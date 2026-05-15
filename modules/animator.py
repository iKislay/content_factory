# modules/animator.py
import os
import subprocess
from typing import List, Dict
import config


class AnimatorError(Exception):
    """Exception raised when animation fails."""
    pass


def animate_scenes(
    image_paths: List[str],
    audio_map: Dict[int, dict],
    scenes: List[dict],
    output_dir: str
) -> List[str]:
    """
    For each scene, applies a Ken Burns (zoom/pan) effect to the image
    using ffmpeg. Duration matches the audio exactly.
    Returns list of animated mp4 file paths in scene_id order.
    """
    os.makedirs(output_dir, exist_ok=True)

    scene_motion = {s["scene_id"]: s["motion_directive"] for s in scenes}

    video_paths = []
    for scene_id in sorted(audio_map.keys()):
        image_path = image_paths[scene_id - 1]
        duration = audio_map[scene_id]["duration"]
        motion = scene_motion.get(scene_id, "static")

        zoompan_filter = _build_zoompan_filter(
            motion, duration, config.VIDEO_FPS, config.IMAGE_WIDTH, config.IMAGE_HEIGHT
        )

        output_path = os.path.join(output_dir, f"video_scene_{scene_id}.mp4")

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", zoompan_filter,
            "-t", str(duration),
            "-r", str(config.VIDEO_FPS),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            raise AnimatorError(f"ffmpeg failed for scene {scene_id}: {result.stderr}")

        video_paths.append(output_path)
        print(f"[ANIMATOR] Scene {scene_id} animated — {motion} ({duration:.2f}s)")

    print(f"[ANIMATOR] Generated {len(video_paths)} animated videos")
    return video_paths


def _build_zoompan_filter(motion: str, duration: float, fps: int, width: int, height: int) -> str:
    """Build ffmpeg zoompan filter string based on motion directive."""
    frames = int(duration * fps)

    filters = {
        "slow zoom in": (
            f"zoompan=z='min(zoom+0.0015,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={fps}"
        ),
        "slow zoom out": (
            f"zoompan=z='if(lte(on,1),1.3,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={fps}"
        ),
        "gentle pan right": (
            f"zoompan=z='1.1':x='if(lte(on,1),0,min(x+2,iw*(1-1/zoom)))':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={fps}"
        ),
        "gentle pan left": (
            f"zoompan=z='1.1':x='if(lte(on,1),iw*0.1,max(0,x-2))':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={fps}"
        ),
        "static": (
            f"zoompan=z='1.0':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={fps}"
        )
    }

    return filters.get(motion, filters["static"])