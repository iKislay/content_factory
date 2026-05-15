# modules/voice.py
import os
import numpy as np
from typing import List, Dict
import config


class VoiceError(Exception):
    """Exception raised when TTS generation fails."""
    pass


def generate_audio(scenes: List[dict], output_dir: str) -> Dict[int, dict]:
    """
    Synthesizes narration for each scene using Kokoro TTS.
    Returns dict mapping scene_id to {"path": str, "duration": float}
    """
    os.makedirs(output_dir, exist_ok=True)

    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf
    except ImportError:
        raise VoiceError(
            "Kokoro not installed. Run: pip install kokoro-onnx soundfile"
        )

    try:
        kokoro = Kokoro.from_pretrained()
    except Exception as e:
        raise VoiceError(f"Failed to load Kokoro model: {e}")

    voices = kokoro.get_voices()
    print(f"[VOICE] Available voices: {voices[:5]}...")

    voice_style = kokoro.get_voice_style(config.KOKORO_VOICE)

    result = {}

    for scene in scenes:
        scene_id = scene["scene_id"]
        narration = scene["narration"]

        try:
            audio, sample_rate = kokoro.create(
                text=narration,
                voice=voice_style,
                speed=1.0,
                lang='en-us'
            )

            output_path = os.path.join(output_dir, f"audio_scene_{scene_id}.wav")
            sf.write(output_path, audio, config.KOKORO_SAMPLE_RATE)

            duration = len(audio) / config.KOKORO_SAMPLE_RATE
            result[scene_id] = {
                "path": output_path,
                "duration": round(duration, 3)
            }

            print(f"[VOICE] Scene {scene_id} synthesized — {duration:.2f}s")

        except Exception as e:
            raise VoiceError(f"Failed to generate audio for scene {scene_id}: {e}")

    print(f"[VOICE] Generated {len(result)} audio files")
    return result