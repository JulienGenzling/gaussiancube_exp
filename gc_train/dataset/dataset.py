import os
import math
import random
import numpy as np
import torch
import json
from torch.utils.data import DataLoader, Dataset
from mpi4py import MPI
from PIL import Image
from utils.script_util import init_volume_grid


def load_data(
    *,
    data_dir,
    batch_size,
    image_size,
    deterministic=False,
    train=True,
    uncond_p=0,
    mean_file=None,
    std_file=None,
    start_idx=-1,
    end_idx=-1,
    txt_file='',
    load_camera=0,
    cam_root_path=None,
    clip_input=True,
    bound=0.45,
    **kwargs,
):
    if not data_dir:
        raise ValueError("unspecified data directory")

    if txt_file != '':
        with open(txt_file) as f:
            all_files = f.read().splitlines()
        all_files = sorted([os.path.join(data_dir, x+'.pt') for x in all_files])
    else:
        all_files = _list_image_files_recursively(data_dir) 

    if start_idx >= 0 and end_idx >= 0 and start_idx < end_idx:
        all_files = all_files[start_idx:end_idx]
    print("Loading files: ", len(all_files))

    dataset = VolumeDataset(
        image_size,
        all_files,
        shard=MPI.COMM_WORLD.Get_rank(),
        num_shards=MPI.COMM_WORLD.Get_size(),
        mean=mean_file,
        std=std_file,
        uncond_p=uncond_p,
        load_camera=load_camera,
        cam_root_path=cam_root_path,
        train=train,
        clip_input=clip_input,
        bound=bound,
    )
    if deterministic:
        loader = DataLoader(
            dataset, batch_size=batch_size, shuffle=False, num_workers=4, drop_last=True, pin_memory=True
        )
    else:
        loader = DataLoader(
            dataset, batch_size=batch_size, shuffle=True, num_workers=4, drop_last=True, pin_memory=True
        )
    while True:
        yield from loader


def _list_image_files_recursively(data_dir):
    results = []
    for entry in sorted(os.listdir(data_dir)):
        full_path = os.path.join(data_dir, entry)
        ext = entry.split(".")[-1]
        if "." in entry and ext.lower() in ["pt"]:
            results.append(full_path)
        elif os.path.isdir(full_path):
            results.extend(_list_image_files_recursively(full_path))
    return results


class VolumeDataset(Dataset):
    def __init__(
        self,
        resolution,
        image_paths,
        shard=0,
        num_shards=1,
        mean=None,
        std=None,
        load_camera=0,
        cam_root_path=None,
        uncond_p=0,
        train=True,
        clip_input=True,
        bound=0.45,
    ):
        super().__init__()
        print("shard, num_shards : ", shard, num_shards)
        self.local_images = image_paths[shard:][::num_shards]
        if mean is not None and std is not None:
            self.mean = torch.load(mean, weights_only=True).to(torch.float32)
            self.std = torch.load(std, weights_only=True).to(torch.float32)
        else:
            self.mean = None
            self.std = None
        self.resolution = resolution
        self.load_camera = load_camera
        self.cam_root_path = cam_root_path
        self.uncond_p = uncond_p
        self.train = train
        self.clip_input = clip_input
        self.std_volume = torch.from_numpy(init_volume_grid(bound=bound, num_pts_each_axis=32)).float()

    def __len__(self):
        return  len(self.local_images)

    def __getitem__(self, idx):
        path = self.local_images[idx]
        data = torch.load(path, weights_only=True).to(torch.float32)
 
        relative_transform = None
        data_dict = {"path": path}

        if self.mean is not None and self.std is not None:
            if len(self.mean.shape) == 1:
                # Apply channel wise normalization
                data = (data - self.mean.reshape(1, 1, 1, -1)).permute(3, 0, 1, 2)
                data_shapes = data.shape
                volume = torch.clip(data.reshape(data_shapes[0], -1).T, -self.std, self.std) / self.std
                volume = volume.T.reshape(data_shapes).permute(1, 2, 3, 0)
            else:
                # Apply instance wise normalization
                volume = (data - self.mean) / self.std
        else:
            volume = data

        volume = volume.permute(3, 0, 1, 2)
        if self.clip_input:
            volume = dynamic_clip(volume, p=0.995)
        
        if self.load_camera > 0:
            if self.train:
                idxes = np.random.randint(0, 150, size=self.load_camera)
            else:
                idxes = range(0, 150)[:self.load_camera]
            root_path = os.path.join(self.cam_root_path, os.path.basename(path).split(".")[0])
            cams = [load_cam(root_path, idx, relative_transform=relative_transform) for idx in idxes]
            data_dict["cams"] = cams
        return volume, data_dict


def load_cam(root_path, frame_idx, trans=np.array([0.0, 0.0, 0.0]), 
             scale=1.0, white_background=True, relative_transform=None):

    camera_path = os.path.join(root_path, "transforms.json")
    with open(camera_path) as json_file:
        contents = json.load(json_file)
        fovx = contents["camera_angle_x"]
        frame = contents["frames"][frame_idx]
        image_path = os.path.join(root_path, frame["file_path"])
        
        original_image = Image.open(image_path)
        im_data = np.array(original_image.convert("RGBA")).astype(np.float32)
        bg = np.array([1,1,1]).astype(np.float32) if white_background else np.array([0, 0, 0]).astype(np.float32)
        norm_data = im_data / 255.0
        alpha = norm_data[:, :, 3:4]
        blurred_alpha = alpha
        # blurred_alpha = cv2.GaussianBlur(alpha, (5, 5), 0)[..., np.newaxis]
        arr = norm_data[:,:,:3] * blurred_alpha + bg * (1 - blurred_alpha)
        image = torch.from_numpy(arr).permute(2, 0, 1)
        
        # NeRF 'transform_matrix' is a camera-to-world transform
        c2w = np.array(frame["transform_matrix"])
        if relative_transform is not None:
            c2w = relative_transform @ c2w
        # change from OpenGL/Blender camera axes (Y up, Z back) to COLMAP (Y down, Z forward)
        c2w[:3, 1:3] *= -1
        # get the world-to-camera transform and set R, T
        w2c = np.linalg.inv(c2w)
        R = np.transpose(w2c[:3,:3])  # R is stored transposed due to 'glm' in CUDA code
        T = w2c[:3, 3]
        fovy = focal2fov(fov2focal(fovx, original_image.size[0]), original_image.size[1])
    
    R = R
    T = T
    FoVx = fovx
    FoVy = fovy
    image_path = image_path

    image_width = original_image.size[1]
    image_height = original_image.size[0]

    zfar = 100.0
    znear = 0.01

    trans = trans
    scale = scale

    world_view_transform = torch.tensor(getWorld2View2(R, T, trans, scale)).transpose(0, 1)
    projection_matrix = getProjectionMatrix(znear=znear, zfar=zfar, fovX=FoVx, fovY=FoVy).transpose(0,1)
    full_proj_transform = (world_view_transform.unsqueeze(0).bmm(projection_matrix.unsqueeze(0))).squeeze(0)
    camera_center = world_view_transform.inverse()[3, :3]

    return {"FoVx": fovx, "FoVy": fovy, "image_width": image_width, "image_height": image_height, "world_view_transform": world_view_transform, "projection_matrix": projection_matrix, "full_proj_transform": full_proj_transform, "camera_center": camera_center, "image": image, "c2w": c2w}


def getWorld2View2(R, t, translate=np.array([.0, .0, .0]), scale=1.0):
    Rt = np.zeros((4, 4))
    Rt[:3, :3] = R.transpose()
    Rt[:3, 3] = t
    Rt[3, 3] = 1.0

    C2W = np.linalg.inv(Rt)
    cam_center = C2W[:3, 3]
    cam_center = (cam_center + translate) * scale
    C2W[:3, 3] = cam_center
    Rt = np.linalg.inv(C2W)
    return np.float32(Rt)


def getProjectionMatrix(znear, zfar, fovX, fovY):
    tanHalfFovY = math.tan((fovY / 2))
    tanHalfFovX = math.tan((fovX / 2))

    top = tanHalfFovY * znear
    bottom = -top
    right = tanHalfFovX * znear
    left = -right

    P = torch.zeros(4, 4)

    z_sign = 1.0

    P[0, 0] = 2.0 * znear / (right - left)
    P[1, 1] = 2.0 * znear / (top - bottom)
    P[0, 2] = (right + left) / (right - left)
    P[1, 2] = (top + bottom) / (top - bottom)
    P[3, 2] = z_sign
    P[2, 2] = z_sign * zfar / (zfar - znear)
    P[2, 3] = -(zfar * znear) / (zfar - znear)
    return P


def fov2focal(fov, pixels):
    return pixels / (2 * math.tan(fov / 2))


def focal2fov(focal, pixels):
    return 2*math.atan(pixels/(2*focal))


def dynamic_clip(x, p=0.995):
    x_shapes = x.shape
    s = torch.quantile(x.abs().reshape(x_shapes[0], -1), p, dim=-1)
    x_compressed = torch.clip(x.reshape(x_shapes[0], -1).T, -s, s)
    x_compressed = x_compressed.T.reshape(x_shapes)
    return x_compressed

