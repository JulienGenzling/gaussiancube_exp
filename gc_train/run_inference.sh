python inference.py \
--exp_name /Data/GaussianCube_data/output/shapenet_diffusion_training \
--config configs/shapenet_uncond.yml  \
--rescale_timesteps 300 \
--ckpt /Data/GaussianCube_data/output/shapenet_diffusion_training/checkpoints/ema_0.9999_2285000.pt \
--mean_file /Data/GaussianCube_data/mean_volume_act.pt  \
--std_file /Data/GaussianCube_data/std_volume_act.pt  \
--bound 0.45 \
--num_samples 4 \
--render_video \
--seed 9 \