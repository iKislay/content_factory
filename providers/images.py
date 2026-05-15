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


import random

def _pollinations_generate(prompt: str, scene_id: int, output_dir: str, max_retries: int = 5) -> str:
    """Generate image using Pollinations.ai."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"image_scene_{scene_id}.jpg"
    filepath = os.path.join(output_dir, filename)

    for attempt in range(max_retries):
        try:
            seed = random.randint(1, 1000000)
            encoded_prompt = quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={config.IMAGE_WIDTH}&height={config.IMAGE_HEIGHT}&nologo=true&seed={seed}"
            
            response = requests.get(url, timeout=60)

            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"[IMG] Generated scene {scene_id} via pollinations")
                return filepath
            else:
                print(f"[IMG] Attempt {attempt + 1} failed with status {response.status_code}")
        except requests.exceptions.Timeout:
            print(f"[IMG] Attempt {attempt + 1} timed out")
        except Exception as e:
            print(f"[IMG] Attempt {attempt + 1} failed: {e}")

        if attempt < max_retries - 1:
            wait_time = (attempt + 1) * 3
            print(f"[IMG] Waiting {wait_time}s before retry...")
            time.sleep(wait_time)

    raise RuntimeError(f"Failed to generate image after {max_retries} attempts")