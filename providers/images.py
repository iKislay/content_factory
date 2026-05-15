# providers/images.py
import requests
import os
from urllib.parse import quote
import time
import config


def generate_image(prompt: str, scene_id: int, output_dir: str) -> str:
    """Generate an image and return local file path."""
    if config.IMAGE_PROVIDER == "pollinations":
        return _pollinations_generate(prompt, scene_id, output_dir)
    else:
        raise ValueError(f"Unknown image provider: {config.IMAGE_PROVIDER}")


def _pollinations_generate(prompt: str, scene_id: int, output_dir: str, max_retries: int = 3) -> str:
    """Generate image using Pollinations.ai."""
    os.makedirs(output_dir, exist_ok=True)

    encoded_prompt = quote(prompt)
    url = f"{config.POLLINATIONS_BASE}/{encoded_prompt}?width={config.IMAGE_WIDTH}&height={config.IMAGE_HEIGHT}&nologo=true&seed={scene_id}"

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                filename = f"image_scene_{scene_id}.jpg"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"[IMG] Generated scene {scene_id} via pollinations")
                return filepath
            else:
                print(f"[IMG] Attempt {attempt + 1} failed with status {response.status_code}")
        except Exception as e:
            print(f"[IMG] Attempt {attempt + 1} failed: {e}")

        if attempt < max_retries - 1:
            time.sleep(2)

    raise RuntimeError(f"Failed to generate image after {max_retries} attempts")