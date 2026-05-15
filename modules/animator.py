# modules/animator.py
from typing import List


def apply_ken_burns(image_paths: List[str], motion_directives: List[str], output_dir: str) -> List[str]:
    """Apply Ken Burns effect to static images."""
    print("[ANIMATOR] stub — not yet implemented")
    return [p.replace(".jpg", "_animated.mp4") for p in image_paths]