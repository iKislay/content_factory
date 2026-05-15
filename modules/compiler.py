# modules/compiler.py
import os
from typing import List, Dict
import config

try:
    # pyrefly: ignore [missing-import]
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

def compile_video(
    video_paths: List[str],
    audio_map: Dict[int, dict],
    output_filename: str = "Final_Automated_Short.mp4"
) -> str:
    """
    Loads each scene video, attaches its audio, concatenates all clips,
    exports the final MP4. Returns the path to the final file.
    """
    # pyrefly: ignore [missing-import]
    from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips

    clips = []

    for video_path in video_paths:
        scene_id = int(os.path.basename(video_path).split("_")[2].split(".")[0])
        audio_info = audio_map[scene_id]

        video_clip = VideoFileClip(video_path)
        audio_clip = AudioFileClip(audio_info["path"])

        # ffmpeg zoompan might produce a video slightly shorter than requested due to fps rounding
        actual_duration = min(video_clip.duration, audio_info["duration"])
        video_clip = video_clip.subclipped(0, actual_duration)
        audio_clip = audio_clip.subclipped(0, actual_duration)
        final_clip = video_clip.with_audio(audio_clip)
        clips.append(final_clip)

    final_video = concatenate_videoclips(clips, method="compose")

    output_path = os.path.join(config.OUTPUT_DIR, output_filename)
    final_video.write_videofile(
        output_path,
        fps=config.VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=os.path.join(config.TEMP_DIR, "temp_audio.m4a"),
        remove_temp=True,
        logger=None
    )

    for clip in clips:
        clip.close()
    final_video.close()

    _cleanup_temp(config.TEMP_DIR)
    print(f"[COMPILER] Final video exported → {output_path}")
    return output_path


def _cleanup_temp(temp_dir: str) -> None:
    """Clean up temporary files in temp directory."""
    if not os.path.exists(temp_dir):
        return

    for f in os.listdir(temp_dir):
        if f.endswith(('.jpg', '.wav', '.mp4', '.m4a')):
            try:
                os.remove(os.path.join(temp_dir, f))
            except Exception:
                pass
    print("[COMPILER] Temp files cleaned up")