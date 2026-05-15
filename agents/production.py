# agents/production.py
"""
ProductionAgent — async fan-out for visual and audio generation.

This agent satisfies "tasks fan out, complete on their own timeline,
return to the planner" by using ThreadPoolExecutor to concurrently
generate all scene images and audio clips.

Tool tracing (Task 3): every generate_image and synthesize_tts invocation
is wrapped in ToolCall / ToolResult dataclasses and posted to the blackboard,
creating a durable, per-scene record of every external API call made during
production — without the LLM overhead of generate_with_tools() per scene.

Fan-out strategy:
  - Submit all 5 image generation tasks to the executor
  - Submit all 5 audio generation tasks to the executor
  - As each future completes, post SCENE_ASSET_READY + TOOL_RESULT messages
  - Once all are done, post PRODUCTION_DONE with the full artifact map

Blackboard messages consumed:
  NARRATIVE_APPROVED  { scenes: List[dict] }  (preferred)
  NARRATIVE_DRAFT     { scenes: List[dict] }  (backward compat)

Blackboard messages produced:
  TOOL_CALLED        { agent, tool_name, arguments, call_id }
  TOOL_RESULT        { agent, tool_name, call_id, output_summary, duration_ms }
  SCENE_ASSET_READY  { scene_id, asset_type, path }
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
                executor.submit(self._generate_single_image, scene, run_id): scene
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

    def _generate_single_image(self, scene: dict, run_id: str) -> str:
        """Generate image for a single scene (runs in thread)."""
        import uuid as _uuid
        from tools.executor import ToolCall, ToolResult

        scene_id = scene["scene_id"]
        prompt = scene["visual_prompt"]
        call_id = str(_uuid.uuid4())[:8]

        # Post TOOL_CALLED before the API request
        self.trace_tool_call(
            run_id,
            ToolCall(
                tool_name="generate_image",
                arguments={"prompt": prompt[:80] + "...", "scene_id": scene_id},
                call_id=call_id,
            ),
            ToolResult(
                tool_name="generate_image",
                call_id=call_id,
                output=None,
                error=None,
                duration_ms=0.0,
            ),
        )

        # Small staggered delay to avoid rate-limiting
        time.sleep((scene_id - 1) * 0.5)

        t0 = time.monotonic()
        try:
            path = image_provider.generate_image(prompt, scene_id, config.TEMP_DIR)
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            # Update with real result — post a TOOL_RESULT
            self.post_message(
                run_id=run_id,
                msg_type="TOOL_RESULT",
                payload={
                    "agent": self.name,
                    "tool_name": "generate_image",
                    "call_id": call_id,
                    "output_summary": path,
                    "error": None,
                    "duration_ms": duration_ms,
                },
            )
            return path
        except Exception as exc:
            self.post_message(
                run_id=run_id,
                msg_type="TOOL_RESULT",
                payload={
                    "agent": self.name,
                    "tool_name": "generate_image",
                    "call_id": call_id,
                    "output_summary": None,
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                },
            )
            raise

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
                    self._generate_single_audio, scene, kokoro, run_id
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

    def _generate_single_audio(self, scene: dict, kokoro, run_id: str) -> Dict[str, Any]:
        """Generate audio for a single scene (runs in thread)."""
        import uuid as _uuid
        import soundfile as sf
        from tools.executor import ToolCall, ToolResult

        scene_id = scene["scene_id"]
        narration = scene["narration"]
        call_id = str(_uuid.uuid4())[:8]

        self.post_message(
            run_id=run_id,
            msg_type="TOOL_CALLED",
            payload={
                "agent": self.name,
                "tool_name": "synthesize_tts",
                "arguments": {"scene_id": scene_id, "text_preview": narration[:60]},
                "call_id": call_id,
            },
        )

        t0 = time.monotonic()
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
        duration = round(len(audio) / config.KOKORO_SAMPLE_RATE, 3)
        duration_ms = round((time.monotonic() - t0) * 1000, 1)

        self.post_message(
            run_id=run_id,
            msg_type="TOOL_RESULT",
            payload={
                "agent": self.name,
                "tool_name": "synthesize_tts",
                "call_id": call_id,
                "output_summary": f"{output_path} ({duration}s)",
                "error": None,
                "duration_ms": duration_ms,
            },
        )

        return {"path": output_path, "duration": duration}
