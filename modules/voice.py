# modules/voice.py
import os
from typing import List, Dict, Any, Optional
import config
from providers.tts import synthesize_speech

class VoiceError(Exception):
    """Exception raised when TTS generation fails."""
    pass

def generate_audio(scenes: List[dict], output_dir: str) -> Dict[int, dict]:
    """
    Synthesizes narration for each scene using the configured TTS provider.
    Returns dict mapping scene_id to {"path": str, "duration": float}
    """
    os.makedirs(output_dir, exist_ok=True)
    result = {}

    # Initialize Kokoro if needed (to avoid reloading for every scene)
    kokoro_model = None
    if config.TTS_PROVIDER == "kokoro":
        kokoro_model = _load_kokoro()

    for scene in scenes:
        scene_id = scene["scene_id"]
        narration = scene["narration"]
        output_path = os.path.join(output_dir, f"audio_scene_{scene_id}.wav")

        try:
            audio_info = synthesize_scene_audio(
                narration, 
                output_path, 
                scene_id, 
                kokoro_model=kokoro_model
            )
            result[scene_id] = audio_info
            print(f"[VOICE] Scene {scene_id} synthesized — {audio_info['duration']:.2f}s")
        except Exception as e:
            raise VoiceError(f"Failed to generate audio for scene {scene_id}: {e}")

    print(f"[VOICE] Generated {len(result)} audio files using {config.TTS_PROVIDER}")
    return result

def synthesize_scene_audio(
    text: str, 
    output_path: str, 
    scene_id: int, 
    kokoro_model: Any = None
) -> Dict[str, Any]:
    """Synthesizes a single piece of text and returns audio info."""
    
    if config.TTS_PROVIDER == "google":
        duration = synthesize_speech(
            text=text,
            output_path=output_path
        )
        if duration is None:
            raise VoiceError("Google TTS synthesis failed")
        return {"path": output_path, "duration": round(duration, 3)}
    
    else:  # Default to Kokoro
        import soundfile as sf
        model = kokoro_model or _load_kokoro()
        voice_style = model.get_voice_style(config.KOKORO_VOICE)
        
        audio, _ = model.create(
            text=text,
            voice=voice_style,
            speed=1.0,
            lang='en-us'
        )
        
        sf.write(output_path, audio, config.KOKORO_SAMPLE_RATE)
        duration = len(audio) / config.KOKORO_SAMPLE_RATE
        return {"path": output_path, "duration": round(duration, 3)}

def _load_kokoro():
    """Load Kokoro TTS model."""
    try:
        from kokoro_onnx import Kokoro
        return Kokoro.from_pretrained()
    except Exception as e:
        raise VoiceError(f"Failed to load Kokoro model: {e}")
