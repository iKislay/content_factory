# modules/visuals.py
import os
from typing import List
from providers import images
import config


def generate_visuals(scenes: List[dict], output_dir: str) -> List[str]:
    """Generate images for all scenes."""
    print("[VISUALS] Generating images for scenes")
    os.makedirs(output_dir, exist_ok=True)

    image_paths = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        prompt = scene["visual_prompt"]
        image_path = images.generate_image(prompt, scene_id, output_dir)
        image_paths.append(image_path)
        print(f"[VISUALS] Generated {image_path}")

    print(f"[VISUALS] Generated {len(image_paths)} images")
    return image_paths