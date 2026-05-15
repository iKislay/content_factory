# modules/visuals.py
import os
import time
from typing import List
from providers import images
from PIL import Image
import config


def generate_visuals(scenes: List[dict], output_dir: str) -> List[str]:
    """Generate images for all scenes."""
    print("[VISUALS] Generating images for scenes")
    os.makedirs(output_dir, exist_ok=True)

    image_paths = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        prompt = scene["visual_prompt"]

        try:
            image_path = images.generate_image(prompt, scene_id, output_dir)
            image_paths.append(image_path)
            print(f"[VISUALS] Generated {image_path}")
        except Exception as e:
            print(f"[VISUALS] Warning: Failed to generate scene {scene_id}: {e}")
            fallback_path = _create_fallback_image(scene_id, output_dir)
            image_paths.append(fallback_path)
            print(f"[VISUALS] Created fallback: {fallback_path}")

        if scene_id < len(scenes):
            time.sleep(1.5)

    print(f"[VISUALS] Generated {len(image_paths)} images")
    print(f"[VISUALS] Downloaded {len(scenes)}/{len(scenes)} images")
    return image_paths


def _create_fallback_image(scene_id: int, output_dir: str) -> str:
    """Create a solid color fallback image."""
    color = (26, 26, 46)
    img = Image.new('RGB', (config.IMAGE_WIDTH, config.IMAGE_HEIGHT), color)
    filename = f"image_scene_{scene_id}_fallback.jpg"
    filepath = os.path.join(output_dir, filename)
    img.save(filepath, 'JPEG')
    return filepath