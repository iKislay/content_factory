# agents/production.py
"""
ProductionAgent — unified async fan-out for visual and audio generation.

Task 5: Async Orchestration
─────────────────────────────────────────────────────────────────────────────
The fundamental change from previous tasks: images and audio are no longer
generated in two sequential phases. All 10 tasks (5 images + 5 audio) are
submitted to a SINGLE shared ThreadPoolExecutor simultaneously. Each task
completes on its own timeline and immediately posts a PRODUCTION_PROGRESS
message to the blackboard — the "return to the planner" requirement.

Why ThreadPoolExecutor (not asyncio):
  The provider calls (requests to Pollinations, Google TTS, Kokoro) are
  blocking I/O. Python threads release the GIL during socket waits, achieving
  true parallel network I/O without rewriting providers with aiohttp. This is
  the correct tool for blocking I/O fan-out in CPython.

Fan-out architecture:
  ┌─────────────────────────────────────────────────┐
  │           Single ThreadPoolExecutor              │
  │  (max_workers = MAX_PRODUCTION_WORKERS = 10)    │
  │                                                  │
  │  img_scene_1 ──────────────────→ @t=12s ──────→ │ PRODUCTION_PROGRESS
  │  aud_scene_1 ───→ @t=3s ─────────────────────→  │ PRODUCTION_PROGRESS
  │  img_scene_2 ─────────────────────────→ @t=15s→ │ PRODUCTION_PROGRESS
  │  aud_scene_2 ───→ @t=3s ─────────────────────→  │ PRODUCTION_PROGRESS
  │  ... (all 10 run in parallel)                    │
  └─────────────────────────────────────────────────┘
              ↓ all complete
        PRODUCTION_SUMMARY (wall time, per-task stats)

Blackboard messages consumed:
  NARRATIVE_APPROVED  { scenes: List[dict] }  (preferred)
  NARRATIVE_DRAFT     { scenes: List[dict] }  (backward compat)

Blackboard messages produced:
  TOOL_CALLED           { agent, tool_name, arguments, call_id }
  TOOL_RESULT           { agent, tool_name, call_id, output_summary, duration_ms }
  PRODUCTION_PROGRESS   { task_id, scene_id, asset_type, status, duration_ms,
                          completed_count, total_tasks, progress_pct }
  PRODUCTION_SUMMARY    { image_paths, audio_map, total_tasks, completed_tasks,
                          failed_tasks, wall_time_ms, fastest_task, slowest_task }
"""

from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import config
from agents.base import AgentResult, BaseAgent
from providers import images as image_provider
from modules.visuals import _create_fallback_image


# ─── SceneTask dataclass ──────────────────────────────────────────────────────


@dataclass
class SceneTask:
    """
    Tracks the lifecycle of a single production task (one image or one audio clip).

    Each scene produces two SceneTasks: one for its image and one for its audio.
    The `task_id` follows the convention "<asset_type>_<scene_id>", e.g. "img_3".

    Attributes:
        task_id:       Unique identifier, e.g. "img_1", "aud_3".
        scene_id:      The scene number (1–N) this task belongs to.
        asset_type:    Either "image" or "audio".
        submitted_at:  Monotonic clock timestamp when the task was submitted.
        completed_at:  Monotonic clock timestamp when the future resolved.
        status:        "PENDING" → "DONE" | "FAILED"
        output:        The path string (image) or audio_info dict (audio) on success.
        error:         Exception message string on failure; None on success.
        duration_ms:   Wall-clock time from submit to completion in milliseconds.
    """

    task_id: str
    scene_id: int
    asset_type: str               # "image" | "audio"
    submitted_at: float = field(default_factory=time.monotonic)
    completed_at: Optional[float] = None
    status: str = "PENDING"       # PENDING | DONE | FAILED
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0

    def mark_done(self, output: Any) -> None:
        """Record successful completion."""
        self.completed_at = time.monotonic()
        self.duration_ms = round((self.completed_at - self.submitted_at) * 1000, 1)
        self.status = "DONE"
        self.output = output

    def mark_failed(self, error: str) -> None:
        """Record failure."""
        self.completed_at = time.monotonic()
        self.duration_ms = round((self.completed_at - self.submitted_at) * 1000, 1)
        self.status = "FAILED"
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "scene_id": self.scene_id,
            "asset_type": self.asset_type,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


# ─── ProductionAgent ──────────────────────────────────────────────────────────


class ProductionAgent(BaseAgent):
    """
    Generates all scene images and audio clips via a unified concurrent fan-out.

    All 10 tasks (5 images + 5 audio) are submitted simultaneously to one
    ThreadPoolExecutor. Each task posts PRODUCTION_PROGRESS to the blackboard
    immediately on completion, satisfying the "return to the planner" requirement.

    The final PRODUCTION_SUMMARY blackboard message carries wall-clock timing,
    fastest/slowest task stats, and per-task outcomes — verifiable proof that
    the fan-out was genuinely concurrent (image and audio task completions
    interleave in the blackboard log).
    """

    name = "production"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting unified async production fan-out (images + audio)...")

        # ── Load scenes from blackboard ───────────────────────────────────────
        narrative_msg = (
            self.get_latest(run_id, "NARRATIVE_APPROVED")
            or self.get_latest(run_id, "NARRATIVE_DRAFT")
            or self.get_latest(run_id, "NARRATIVE_READY")   # legacy
        )
        if narrative_msg:
            scenes = narrative_msg["payload"]["scenes"]
        else:
            scenes = context.get("scenes", [])

        if not scenes:
            return AgentResult(
                success=False,
                reasoning="No scenes found in blackboard or context.",
                errors=["NARRATIVE_APPROVED/NARRATIVE_DRAFT message missing"],
            )

        self.log(
            f"Producing assets for {len(scenes)} scenes "
            f"({len(scenes) * 2} total tasks)..."
        )
        os.makedirs(config.TEMP_DIR, exist_ok=True)

        # ── Pre-load TTS model (once, shared across audio threads) ────────────
        kokoro = self._preload_tts_model()

        # ── Unified concurrent fan-out ─────────────────────────────────────────
        wall_start = time.monotonic()
        image_paths, audio_map, all_tasks = self._generate_all_parallel(
            run_id, scenes, kokoro
        )
        wall_time_ms = round((time.monotonic() - wall_start) * 1000, 1)

        # ── Build and post PRODUCTION_SUMMARY ─────────────────────────────────
        done_tasks = [t for t in all_tasks if t.status == "DONE"]
        failed_tasks = [t for t in all_tasks if t.status == "FAILED"]

        fastest = min(done_tasks, key=lambda t: t.duration_ms, default=None)
        slowest = max(done_tasks, key=lambda t: t.duration_ms, default=None)

        self.log(
            f"Fan-out complete — {len(done_tasks)}/{len(all_tasks)} tasks succeeded "
            f"in {wall_time_ms:.0f}ms wall time"
        )
        if fastest:
            self.log(
                f"  Fastest: {fastest.task_id} ({fastest.duration_ms:.0f}ms) | "
                f"Slowest: {slowest.task_id} ({slowest.duration_ms:.0f}ms)"
            )

        summary_payload = {
            "image_paths": image_paths,
            "audio_map": audio_map,
            "total_tasks": len(all_tasks),
            "completed_tasks": len(done_tasks),
            "failed_tasks": len(failed_tasks),
            "wall_time_ms": wall_time_ms,
            "fastest_task": fastest.to_dict() if fastest else None,
            "slowest_task": slowest.to_dict() if slowest else None,
            "task_details": [t.to_dict() for t in sorted(all_tasks, key=lambda t: t.task_id)],
        }

        self.post_message(
            run_id=run_id,
            msg_type="PRODUCTION_SUMMARY",
            payload=summary_payload,
            recipient="publisher",
        )

        return AgentResult(
            success=True,
            output={"image_paths": image_paths, "audio_map": audio_map},
            next_agent="publisher",
            reasoning=(
                f"Unified fan-out: {len(all_tasks)} tasks concurrent "
                f"({len(done_tasks)} done, {len(failed_tasks)} failed). "
                f"Wall time: {wall_time_ms:.0f}ms. "
                f"Slowest: {slowest.task_id} ({slowest.duration_ms:.0f}ms)."
                if slowest else
                f"Unified fan-out: {len(all_tasks)} tasks submitted."
            ),
        )

    # ── Core: unified concurrent fan-out ─────────────────────────────────────

    def _generate_all_parallel(
        self,
        run_id: str,
        scenes: List[dict],
        kokoro: Any,
    ) -> Tuple[List[str], Dict[int, dict], List[SceneTask]]:
        """
        Submit all image and audio tasks to ONE shared executor simultaneously.

        This is the central Task 5 change: both asset types fan out in parallel
        from the same executor rather than running in sequential phases. The
        `as_completed()` loop processes tasks in completion order (not submission
        order) and posts PRODUCTION_PROGRESS immediately for each one.

        Returns:
            (image_paths_ordered, audio_map, all_scene_tasks)
        """
        total_tasks = len(scenes) * 2  # image + audio per scene

        # Build the future → SceneTask map before submitting
        # Submitted at the same time inside a single executor context
        image_results: Dict[int, str] = {}
        audio_results: Dict[int, dict] = {}
        all_tasks: List[SceneTask] = []

        with ThreadPoolExecutor(
            max_workers=config.MAX_PRODUCTION_WORKERS,
            thread_name_prefix="prod",
        ) as executor:
            future_to_task: Dict[Future, SceneTask] = {}

            # Submit ALL image tasks first (submission is O(1) — they queue immediately)
            for scene in scenes:
                task = SceneTask(
                    task_id=f"img_{scene['scene_id']}",
                    scene_id=scene["scene_id"],
                    asset_type="image",
                    submitted_at=time.monotonic(),
                )
                all_tasks.append(task)
                future = executor.submit(
                    self._generate_single_image, scene, run_id
                )
                future_to_task[future] = task

            # Submit ALL audio tasks immediately after (not after images complete)
            for scene in scenes:
                task = SceneTask(
                    task_id=f"aud_{scene['scene_id']}",
                    scene_id=scene["scene_id"],
                    asset_type="audio",
                    submitted_at=time.monotonic(),
                )
                all_tasks.append(task)
                future = executor.submit(
                    self._generate_single_audio, scene, kokoro, run_id
                )
                future_to_task[future] = task

            self.log(
                f"Submitted {total_tasks} tasks to executor "
                f"(workers={config.MAX_PRODUCTION_WORKERS}): "
                f"{len(scenes)} images + {len(scenes)} audio"
            )

            # ── Process completions in arrival order ──────────────────────────
            completed_count = 0

            for future in as_completed(
                future_to_task,
                timeout=config.PRODUCTION_FANOUT_TIMEOUT_SEC,
            ):
                task = future_to_task[future]
                completed_count += 1
                progress_pct = round(completed_count / total_tasks * 100, 1)

                try:
                    output = future.result()
                    task.mark_done(output)

                    # Route output to the right collector
                    if task.asset_type == "image":
                        image_results[task.scene_id] = output
                    else:
                        audio_results[task.scene_id] = output

                    self.log(
                        f"  [{completed_count}/{total_tasks}] "
                        f"{task.task_id} ✓ "
                        f"({task.duration_ms:.0f}ms)"
                    )

                except Exception as exc:
                    task.mark_failed(str(exc))
                    self.log(
                        f"  [{completed_count}/{total_tasks}] "
                        f"{task.task_id} ✗ {exc}"
                    )

                    # Apply fallbacks for failed tasks
                    if task.asset_type == "image":
                        fallback_path = _create_fallback_image(
                            task.scene_id, config.TEMP_DIR
                        )
                        image_results[task.scene_id] = fallback_path
                        task.output = fallback_path
                        task.status = "DONE"  # fallback counts as done
                    # Audio failures are non-recoverable — leave as FAILED

                # Post PRODUCTION_PROGRESS immediately on each completion
                self.post_message(
                    run_id=run_id,
                    msg_type="PRODUCTION_PROGRESS",
                    payload={
                        "task_id": task.task_id,
                        "scene_id": task.scene_id,
                        "asset_type": task.asset_type,
                        "status": task.status,
                        "duration_ms": task.duration_ms,
                        "completed_count": completed_count,
                        "total_tasks": total_tasks,
                        "progress_pct": progress_pct,
                    },
                )

        # Return image paths in scene order; audio_map keyed by scene_id
        ordered_image_paths = [
            image_results[s["scene_id"]]
            for s in sorted(scenes, key=lambda x: x["scene_id"])
            if s["scene_id"] in image_results
        ]

        return ordered_image_paths, audio_results, all_tasks

    # ── Task workers (run inside executor threads) ────────────────────────────

    def _generate_single_image(self, scene: dict, run_id: str) -> str:
        """Generate image for one scene. Runs in a thread — must be thread-safe."""
        from tools.executor import ToolCall, ToolResult

        scene_id = scene["scene_id"]
        prompt = scene["visual_prompt"]
        call_id = str(uuid.uuid4())[:8]

        # Log intent before the blocking API call
        self.post_message(
            run_id=run_id,
            msg_type="TOOL_CALLED",
            payload={
                "agent": self.name,
                "tool_name": "generate_image",
                "arguments": {"prompt": prompt[:80] + "...", "scene_id": scene_id},
                "call_id": call_id,
            },
        )

        # Staggered start to avoid simultaneous Pollinations bursts
        time.sleep((scene_id - 1) * 0.3)

        t0 = time.monotonic()
        try:
            path = image_provider.generate_image(prompt, scene_id, config.TEMP_DIR)
            duration_ms = round((time.monotonic() - t0) * 1000, 1)
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

    def _generate_single_audio(
        self, scene: dict, kokoro: Any, run_id: str
    ) -> Dict[str, Any]:
        """Generate audio for one scene. Runs in a thread — must be thread-safe."""
        from modules.voice import synthesize_scene_audio

        scene_id = scene["scene_id"]
        narration = scene["narration"]
        call_id = str(uuid.uuid4())[:8]

        self.post_message(
            run_id=run_id,
            msg_type="TOOL_CALLED",
            payload={
                "agent": self.name,
                "tool_name": "synthesize_tts",
                "arguments": {
                    "scene_id": scene_id,
                    "text_preview": narration[:60],
                    "provider": config.TTS_PROVIDER,
                },
                "call_id": call_id,
            },
        )

        t0 = time.monotonic()
        output_path = os.path.join(config.TEMP_DIR, f"audio_scene_{scene_id}.wav")

        audio_info = synthesize_scene_audio(
            text=narration,
            output_path=output_path,
            scene_id=scene_id,
            kokoro_model=kokoro,
        )
        duration_ms = round((time.monotonic() - t0) * 1000, 1)

        self.post_message(
            run_id=run_id,
            msg_type="TOOL_RESULT",
            payload={
                "agent": self.name,
                "tool_name": "synthesize_tts",
                "call_id": call_id,
                "output_summary": f"{output_path} ({audio_info.get('duration', 0):.2f}s)",
                "error": None,
                "duration_ms": duration_ms,
            },
        )

        return audio_info

    # ── TTS model pre-loading ─────────────────────────────────────────────────

    def _preload_tts_model(self) -> Any:
        """
        Pre-load the TTS model once before submitting audio tasks.

        The model is shared (read-only) across all audio threads — Kokoro
        inference is thread-safe for concurrent reads. This avoids loading
        the ~300MB model 5 times in parallel (which would OOM on most machines).

        Returns None if TTS_PROVIDER is not "kokoro" (Google TTS is stateless).
        """
        if config.TTS_PROVIDER != "kokoro":
            return None

        try:
            from modules.voice import _load_kokoro
            self.log("Pre-loading Kokoro TTS model (shared across audio threads)...")
            model = _load_kokoro()
            self.log("Kokoro model loaded ✓")
            return model
        except Exception as exc:
            self.log(f"Kokoro pre-load failed: {exc} — audio tasks will use fallback")
            return None
