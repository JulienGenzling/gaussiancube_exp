import os
import torch

path = "/Data/GaussianCube_data/output_gaussiancube/volume_act"

all_pt = []

for p in os.listdir(path):
    full_path = os.path.join(path, p)
    all_pt.append(torch.load(full_path, weights_only=True))

mean = torch.mean(torch.stack(all_pt), dim=0)
std = torch.std(torch.stack(all_pt), dim=0)

print(mean.shape, std.shape)

#Save the tensors
torch.save(mean, "/Data/GaussianCube_data/mean_volume_act.pt")
torch.save(std, "/Data/GaussianCube_data/std_volume_act.pt")