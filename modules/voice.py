# modules/voice.py
from typing import List


def generate_voice(scenes: List[dict], output_dir: str) -> List[str]:
    """Generate TTS audio for each scene narration."""
    print("[VOICE] stub — not yet implemented")
    return [f"audio_scene_{s['scene_id']}.wav" for s in scenes]