# agents/production.py
"""
ProductionAgent — async fan-out for visual and audio generation.

This agent satisfies "tasks fan out, complete on their own timeline,
return to the planner" by using ThreadPoolExecutor to concurrently
generate all scene images and audio clips, rather than sequentially
processing each scene.

Fan-out strategy:
  - Submit all 5 image generation tasks to the executor
  - Submit all 5 audio generation tasks to the executor
  - As each future completes, post a SCENE_ASSET_READY message to
    the blackboard (live progress trace)
  - Once all are done, post PRODUCTION_DONE with the full artifact map

Blackboard messages consumed:
  NARRATIVE_READY  { scenes: List[dict] }

Blackboard messages produced:
  SCENE_ASSET_READY  { scene_id, asset_type, path }  (one per scene per asset)
  PRODUCTION_DONE    { image_paths, audio_map }
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import Any, Dict, List, Optional, Tuple

import config
from agents.base import AgentResult, BaseAgent
from providers import images as image_provider
from modules.visuals import _create_fallback_image
from state import PipelineState


class ProductionAgent(BaseAgent):
    """
    Concurrently generates all scene images and audio clips.

    Uses a ThreadPoolExecutor to fan out work across scenes. Each completed
    future posts a live SCENE_ASSET_READY message to the blackboard before
    the full PRODUCTION_DONE is posted, giving the Orchestrator (and any
    observer) real-time visibility into production progress.
    """

    name = "production"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting async production fan-out...")

        # Read scenes from blackboard — prefer NARRATIVE_APPROVED (post-Critic)
        # Fall back to NARRATIVE_DRAFT for backward compatibility
        narrative_msg = (
            self.get_latest(run_id, "NARRATIVE_APPROVED")
            or self.get_latest(run_id, "NARRATIVE_DRAFT")
            or self.get_latest(run_id, "NARRATIVE_READY")  # legacy
        )
        if narrative_msg:
            scenes = narrative_msg["payload"]["scenes"]
        else:
            scenes = context.get("scenes", [])

        if not scenes:
            return AgentResult(
                success=False,
                reasoning="No scenes found in blackboard or context.",
                errors=["NARRATIVE_READY message missing"],
            )

        self.log(f"Producing assets for {len(scenes)} scenes...")

        os.makedirs(config.TEMP_DIR, exist_ok=True)

        # ── Phase 1: Image fan-out ────────────────────────────────────────────
        image_paths = self._generate_images_parallel(run_id, scenes)

        # ── Phase 2: Audio fan-out ────────────────────────────────────────────
        audio_map = self._generate_audio_parallel(run_id, scenes)

        self.log(
            f"Production complete — {len(image_paths)} images, "
            f"{len(audio_map)} audio clips"
        )

        self.post_message(
            run_id=run_id,
            msg_type="PRODUCTION_DONE",
            payload={
                "image_paths": image_paths,
                "audio_map": audio_map,
            },
            recipient="publisher",
        )

        return AgentResult(
            success=True,
            output={"image_paths": image_paths, "audio_map": audio_map},
            next_agent="publisher",
            reasoning=(
                f"Generated {len(image_paths)} images and {len(audio_map)} "
                f"audio clips using ThreadPoolExecutor "
                f"(max_workers={config.MAX_PRODUCTION_WORKERS})."
            ),
        )

    # ── Image generation ──────────────────────────────────────────────────────

    def _generate_images_parallel(
        self, run_id: str, scenes: List[dict]
    ) -> List[str]:
        """Fan out image generation for all scenes."""
        self.log(
            f"Submitting {len(scenes)} image tasks "
            f"(workers={config.MAX_PRODUCTION_WORKERS})..."
        )
        image_paths: Dict[int, str] = {}

        with ThreadPoolExecutor(
            max_workers=config.MAX_PRODUCTION_WORKERS,
            thread_name_prefix="img",
        ) as executor:
            future_to_scene: Dict[Future, dict] = {
                executor.submit(self._generate_single_image, scene): scene
                for scene in scenes
            }

            for future in as_completed(future_to_scene):
                scene = future_to_scene[future]
                scene_id = scene["scene_id"]
                try:
                    path = future.result()
                    image_paths[scene_id] = path
                    self.log(f"  Image ready → scene {scene_id}: {path}")
                    self.post_message(
                        run_id=run_id,
                        msg_type="SCENE_ASSET_READY",
                        payload={
                            "scene_id": scene_id,
                            "asset_type": "image",
                            "path": path,
                        },
                    )
                except Exception as e:
                    self.log(f"  Image FAILED scene {scene_id}: {e} — using fallback")
                    path = _create_fallback_image(scene_id, config.TEMP_DIR)
                    image_paths[scene_id] = path
                    self.post_message(
                        run_id=run_id,
                        msg_type="SCENE_ASSET_READY",
                        payload={
                            "scene_id": scene_id,
                            "asset_type": "image",
                            "path": path,
                            "fallback": True,
                        },
                    )

        # Return as ordered list (scene_id 1..N)
        return [image_paths[s["scene_id"]] for s in sorted(scenes, key=lambda x: x["scene_id"])]

    def _generate_single_image(self, scene: dict) -> str:
        """Generate image for a single scene (runs in thread)."""
        scene_id = scene["scene_id"]
        prompt = scene["visual_prompt"]
        # Small staggered delay to avoid hammering Pollinations rate limits
        time.sleep((scene_id - 1) * 0.5)
        return image_provider.generate_image(prompt, scene_id, config.TEMP_DIR)

    # ── Audio generation ──────────────────────────────────────────────────────

    def _generate_audio_parallel(
        self, run_id: str, scenes: List[dict]
    ) -> Dict[int, dict]:
        """Fan out audio generation for all scenes."""
        self.log(f"Loading Kokoro TTS model...")
        kokoro = self._load_kokoro()

        self.log(
            f"Submitting {len(scenes)} audio tasks "
            f"(workers={config.MAX_PRODUCTION_WORKERS})..."
        )
        audio_map: Dict[int, dict] = {}

        with ThreadPoolExecutor(
            max_workers=config.MAX_PRODUCTION_WORKERS,
            thread_name_prefix="aud",
        ) as executor:
            future_to_scene: Dict[Future, dict] = {
                executor.submit(
                    self._generate_single_audio, scene, kokoro
                ): scene
                for scene in scenes
            }

            for future in as_completed(future_to_scene):
                scene = future_to_scene[future]
                scene_id = scene["scene_id"]
                try:
                    audio_info = future.result()
                    audio_map[scene_id] = audio_info
                    self.log(
                        f"  Audio ready → scene {scene_id}: "
                        f"{audio_info['duration']:.2f}s"
                    )
                    self.post_message(
                        run_id=run_id,
                        msg_type="SCENE_ASSET_READY",
                        payload={
                            "scene_id": scene_id,
                            "asset_type": "audio",
                            "path": audio_info["path"],
                            "duration": audio_info["duration"],
                        },
                    )
                except Exception as e:
                    raise RuntimeError(
                        f"Audio generation failed for scene {scene_id}: {e}"
                    )

        return audio_map

    def _load_kokoro(self):
        """Load Kokoro TTS model — fails fast with a clear error."""
        try:
            from kokoro_onnx import Kokoro
            return Kokoro.from_pretrained()
        except ImportError:
            raise RuntimeError(
                "Kokoro TTS not installed. Run: pip install kokoro-onnx soundfile"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load Kokoro model: {e}")

    def _generate_single_audio(self, scene: dict, kokoro) -> Dict[str, Any]:
        """Generate audio for a single scene (runs in thread)."""
        import soundfile as sf
        import numpy as np

        scene_id = scene["scene_id"]
        narration = scene["narration"]

        voice_style = kokoro.get_voice_style(config.KOKORO_VOICE)
        audio, _ = kokoro.create(
            text=narration,
            voice=voice_style,
            speed=1.0,
            lang="en-us",
        )

        output_path = os.path.join(
            config.TEMP_DIR, f"audio_scene_{scene_id}.wav"
        )
        sf.write(output_path, audio, config.KOKORO_SAMPLE_RATE)

        duration = len(audio) / config.KOKORO_SAMPLE_RATE
        return {"path": output_path, "duration": round(duration, 3)}
