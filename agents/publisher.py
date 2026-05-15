# agents/publisher.py
"""
PublisherAgent — compiles the final video and fires the Discord webhook.

Responsibilities:
  1. Read PRODUCTION_DONE from blackboard to get all scene assets
  2. Read NARRATIVE_READY to get scenes (for audio sync + animation)
  3. Run ffmpeg animation (Ken Burns effects) on each scene image+audio pair
  4. Concatenate all clips into the final MP4 via moviepy
  5. Post the video to Discord via webhook
  6. Post PUBLISHED to the blackboard with outcome

Blackboard messages consumed:
  PRODUCTION_DONE  { image_paths, audio_map }
  NARRATIVE_READY  { scenes }

Blackboard messages produced:
  VIDEO_COMPILED   { video_path }
  PUBLISHED        { video_path, discord_success, topic }
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import config
from agents.base import AgentResult, BaseAgent
from modules.animator import animate_scenes
from modules.compiler import compile_video
from modules.publisher import publish
from state import PipelineState


class PublisherAgent(BaseAgent):
    """
    Compiles and publishes the final video.

    Reads all production assets from the blackboard, runs the animation
    pipeline (Ken Burns effects via ffmpeg), concatenates via moviepy,
    then fires the Discord webhook as the verifiable external side-effect.
    """

    name = "publisher"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting video compilation and publishing...")

        # ── Load assets from blackboard ────────────────────────────────────────
        production_msg = self.get_latest(run_id, "PRODUCTION_DONE")
        # Prefer NARRATIVE_APPROVED (post-Critic); fall back for legacy runs
        narrative_msg = (
            self.get_latest(run_id, "NARRATIVE_APPROVED")
            or self.get_latest(run_id, "NARRATIVE_DRAFT")
            or self.get_latest(run_id, "NARRATIVE_READY")  # legacy
        )

        if not production_msg:
            return AgentResult(
                success=False,
                reasoning="PRODUCTION_DONE message missing from blackboard.",
                errors=["No production assets found"],
            )

        image_paths: List[str] = production_msg["payload"]["image_paths"]
        audio_map: Dict[int, dict] = {
            int(k): v
            for k, v in production_msg["payload"]["audio_map"].items()
        }

        scenes: List[dict] = []
        topic = context.get("topic", "")
        if narrative_msg:
            scenes = narrative_msg["payload"]["scenes"]
            topic = narrative_msg["payload"].get("topic", topic)

        self.log(
            f"Assets loaded — {len(image_paths)} images, "
            f"{len(audio_map)} audio clips, topic: '{topic}'"
        )

        # ── Step 1: Animate (Ken Burns effects) ───────────────────────────────
        self.log("Step 1/3 — Animating scenes (Ken Burns effects)...")
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)

        video_paths = animate_scenes(
            image_paths, audio_map, scenes, config.TEMP_DIR
        )
        self.log(f"Animation done — {len(video_paths)} clips")

        # ── Step 2: Compile final video ────────────────────────────────────────
        self.log("Step 2/3 — Compiling final video...")
        final_path = compile_video(video_paths, audio_map)
        self.log(f"Compiled → {final_path}")

        self.post_message(
            run_id=run_id,
            msg_type="VIDEO_COMPILED",
            payload={"video_path": final_path, "topic": topic},
        )

        # ── Step 3: Publish to Discord ─────────────────────────────────────────
        self.log("Step 3/3 — Publishing to Discord webhook...")
        discord_ok = publish(final_path, topic)

        if discord_ok:
            self.log("Published to Discord ✓")
        else:
            self.log("Discord publish skipped or failed (non-fatal)")

        self.post_message(
            run_id=run_id,
            msg_type="PUBLISHED",
            payload={
                "video_path": final_path,
                "discord_success": discord_ok,
                "topic": topic,
            },
        )

        errors = [] if discord_ok else ["Discord webhook not configured or failed"]

        return AgentResult(
            success=True,
            output={
                "final_path": final_path,
                "discord_success": discord_ok,
                "topic": topic,
            },
            next_agent=None,  # terminal agent
            reasoning=(
                f"Compiled {len(video_paths)} clips into '{final_path}'. "
                f"Discord publish: {'success' if discord_ok else 'skipped/failed'}."
            ),
            errors=errors,
        )
