import os
import json
import argparse
import multiprocessing

parser = argparse.ArgumentParser(description='Renders given obj file by rotating a camera around it.')
parser.add_argument(
    '--save_folder', type=str, default='./tmp',
    help='path for saving rendered image')
parser.add_argument(
    '--dataset_folder', type=str, default='./tmp',
    help='path for downloaded 3d dataset folder')
parser.add_argument(
    '--blender_root', type=str, default='./tmp',
    help='path for blender')
parser.add_argument(
    '--num_workers', type=int, default=5,
    help='number of workers for multiprocessing')
parser.add_argument(
    '--node', type=str, default="quiscale",
    help='name of the node')
args = parser.parse_args()

save_folder = args.save_folder
dataset_folder = args.dataset_folder
blender_root = args.blender_root

with open("folds.json", 'r') as f:
    folds = json.load(f)
    synset_folders = folds[args.node]

os.makedirs(args.save_folder, exist_ok=True)

with open(f"{args.save_folder}/shapenet_airplane.txt", 'w') as txt_file:
    for item in synset_folders:
        txt_file.write(item + "\n")

def render_object(params):
    file, obj_scale = params
    file_path = os.path.join(dataset_folder, '02691156', file, 'models', 'model_normalized.obj')
    render_cmd = f'{blender_root} -b -P render_shapenet.py -- --output {save_folder} {file_path} --scale {obj_scale} --views 150 --resolution 512'
    os.system(render_cmd)

obj_scale = 0.9

params = [(folder, obj_scale) for folder in synset_folders]

with multiprocessing.Pool(processes=args.num_workers) as pool:
    pool.map(render_object, params)
