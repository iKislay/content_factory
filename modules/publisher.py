# modules/publisher.py
import os
import requests
import config


def publish(video_path: str, topic: str) -> bool:
    """
    Posts the final MP4 to Discord via webhook.
    Returns True on success, False on failure.
    """
    if not config.DISCORD_WEBHOOK_URL:
        print("[PUBLISHER] Discord webhook not configured, skipping")
        return False

    if not os.path.exists(video_path):
        print(f"[PUBLISHER] Video file not found: {video_path}")
        return False

    try:
        with open(video_path, "rb") as f:
            response = requests.post(
                config.DISCORD_WEBHOOK_URL,
                data={
                    "content": f"🎬 **New Auto-Generated Short**\n📌 Topic: *{topic}*"
                },
                files={
                    "file": (os.path.basename(video_path), f, "video/mp4")
                },
                timeout=60
            )

        if response.status_code in (200, 204):
            print("[PUBLISHER] Posted to Discord ✓")
            return True
        else:
            print(f"[PUBLISHER] Discord post failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"[PUBLISHER] Error posting to Discord: {e}")
        return False


def publish_video(video_path: str, topic: str = "") -> bool:
    """Alias for publish() for backward compatibility."""
    return publish(video_path, topic)