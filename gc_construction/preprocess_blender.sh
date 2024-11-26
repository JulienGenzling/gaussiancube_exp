node=$1

python render_all.py \
--save_folder /Data/GaussianCube_data/blender_preprocessed \
--dataset_folder /Data/ShapeNetCore \
--blender_root /users/eleves-b/2021/julien.genzling/blender-2.90.0-linux64/blender \
--num_workers 5 \
--node "$node"