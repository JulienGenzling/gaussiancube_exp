import open3d as o3d
import numpy as np
import os

def capture_screenshots(mesh_path, num_views=36, output_dir='screenshots'):
    os.makedirs(output_dir, exist_ok=True)
    
    # Load the mesh
    mesh = o3d.io.read_triangle_mesh(mesh_path)
    mesh.compute_vertex_normals()

    # Create a scene
    vis = o3d.visualization.Visualizer()
    vis.create_window(visible=False)  # Create a window in headless mode

    # Add the mesh to the visualizer
    vis.add_geometry(mesh)

    # Set the camera parameters
    for i in range(num_views):
        angle = 2 * np.pi * i / num_views
        radius = 2.0
        camera_position = [radius * np.cos(angle), radius * np.sin(angle), 1.0]

        # Set the camera view
        vis.get_view_control().set_front(camera_position)
        vis.get_view_control().set_lookat([0, 0, 0])
        vis.get_view_control().set_up([0, 0, 1])

        # Capture the screenshot
        vis.poll_events()
        vis.update_renderer()
        vis.capture_screen_image(f"{output_dir}/screenshot_{i:03d}.png", do_render=True)

    vis.destroy_window()

# Usage

capture_screenshots('/Data/ShapeNetCore/02958343/1a0bc9ab92c915167ae33d942430658c/models/model_normalized.obj', num_views=150)
