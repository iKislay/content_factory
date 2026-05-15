# agents/orchestrator.py
"""
OrchestratorAgent — the brain of the multi-agent pipeline.

The Orchestrator is responsible for:
  1. Planning: Declaring the full execution plan upfront ("I will run X → Y → Z")
  2. Routing: Deciding which agent to invoke next based on pipeline state
  3. Crash Recovery: On restart, reading the blackboard to determine the
     exact point of failure and resume from there
  4. Reflection: After each agent completes, logging its reasoning before
     proceeding to the next step
  5. Failure Handling: Retry logic with exponential backoff; graceful
     degradation where possible (e.g., production fails → mark run as failed)

Pipeline status → Agent mapping:
  PENDING        → TrendScoutAgent  (discover topic)
  NARRATED       → ProductionAgent  (generate assets — images + audio)
  AUDIO_DONE     → PublisherAgent   (compile + publish)
  COMPILED       → PublisherAgent   (publish only, video already compiled)
  DONE           → (no-op)

Note: We use the existing PipelineState status field as the authoritative
resume checkpoint. The blackboard messages provide the detailed artifact
payloads and causal trace.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Type

from agents.base import AgentResult, BaseAgent
from agents.trend_scout import TrendScoutAgent
from agents.narrator import NarratorAgent
from agents.production import ProductionAgent
from agents.publisher import PublisherAgent
from state import PipelineState


# ─── Status → Next Agent mapping ──────────────────────────────────────────────

_STATUS_TO_AGENT: Dict[str, Optional[str]] = {
    "PENDING":       "trend_scout",
    "NARRATED":      "production",
    "VISUALS_DONE":  "production",   # legacy: treat as needing production redo
    "AUDIO_DONE":    "publisher",
    "ANIMATED":      "publisher",
    "COMPILED":      "publisher",
    "DONE":          None,
}

_AGENT_PRODUCES_STATUS: Dict[str, str] = {
    "trend_scout": "PENDING",    # TrendScout → run creates PENDING, Narrator advances it
    "narrator":    "NARRATED",
    "production":  "AUDIO_DONE",
    "publisher":   "DONE",
}


class OrchestratorAgent(BaseAgent):
    """
    Plans, routes, and reflects across the full pipeline lifecycle.

    The Orchestrator is not itself a worker — it delegates to specialist
    agents and observes their results. Its key value-add is the planning
    and reflection layer that makes the system feel autonomous rather than
    scripted.
    """

    name = "orchestrator"

    def __init__(self, state: PipelineState) -> None:
        super().__init__(state)
        self._agents: Dict[str, BaseAgent] = {
            "trend_scout": TrendScoutAgent(state),
            "narrator":    NarratorAgent(state),
            "production":  ProductionAgent(state),
            "publisher":   PublisherAgent(state),
        }

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self, run_id: Optional[str] = None, context: Dict[str, Any] = {}) -> AgentResult:
        """
        Run the full pipeline for the given run_id (or discover a pending one).
        """
        # ── Resolve or create the run ─────────────────────────────────────────
        run_id, is_resume, topic = self._resolve_run(run_id)

        # ── Declare the execution plan ────────────────────────────────────────
        self._declare_plan(run_id, is_resume, topic)

        # ── Agent dispatch loop ───────────────────────────────────────────────
        status = self.state.get_run_status(run_id)
        ctx: Dict[str, Any] = {"topic": topic}

        while True:
            next_agent_name = _STATUS_TO_AGENT.get(status)

            if next_agent_name is None:
                self.log(f"Run {run_id[:8]} is {status} — nothing to do.")
                break

            self.log(
                f"Status: {status} → dispatching to [{next_agent_name.upper()}]"
            )

            result = self._dispatch(next_agent_name, run_id, ctx)

            # ── Reflect on result ─────────────────────────────────────────────
            self._reflect(next_agent_name, result)

            if not result.success:
                self.log(
                    f"Agent [{next_agent_name.upper()}] failed — "
                    f"errors: {result.errors}"
                )
                self.post_message(
                    run_id=run_id,
                    msg_type="AGENT_FAILED",
                    payload={
                        "agent": next_agent_name,
                        "errors": result.errors,
                        "reasoning": result.reasoning,
                    },
                )
                return result

            # ── Advance pipeline status ────────────────────────────────────────
            new_status = self._advance_status(
                next_agent_name, run_id, result, ctx
            )
            status = new_status

            if status == "DONE":
                break

        final_path = self.state.get_final_path(run_id)
        self.log(f"Pipeline complete ✓  run={run_id[:8]}  output={final_path}")

        self.post_message(
            run_id=run_id,
            msg_type="PIPELINE_COMPLETE",
            payload={"run_id": run_id, "final_path": final_path},
        )

        return AgentResult(
            success=True,
            output={"run_id": run_id, "final_path": final_path},
            reasoning="Full pipeline completed successfully.",
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve_run(self, run_id: Optional[str]) -> tuple[str, bool, str]:
        """Resolve the run to use — resume pending or create new."""
        if run_id:
            run = self.state.get_run_status(run_id)
            topic_msg = self.state.get_latest_message(run_id, "TOPIC_SELECTED")
            topic = topic_msg["payload"]["topic"] if topic_msg else ""
            return run_id, True, topic

        pending = self.state.get_pending_run()
        if pending:
            self.log(
                f"Resuming run {pending['run_id'][:8]} "
                f"(status={pending['status']}, topic='{pending['topic']}')"
            )
            return pending["run_id"], True, pending["topic"]

        # New run — create a placeholder; TrendScout will set the topic
        placeholder_run_id = self.state.create_run("TBD")
        self.log(f"New run created: {placeholder_run_id[:8]}")
        return placeholder_run_id, False, ""

    def _declare_plan(self, run_id: str, is_resume: bool, topic: str) -> None:
        """Log and record the execution plan before any agent runs."""
        status = self.state.get_run_status(run_id)
        remaining = self._get_remaining_agents(status)

        if is_resume and topic:
            self.log(
                f"RESUMING run {run_id[:8]} — topic: '{topic}' — "
                f"status: {status}"
            )
        else:
            self.log(f"STARTING new run {run_id[:8]}")

        plan = " → ".join(a.upper() for a in remaining) if remaining else "DONE"
        self.log(f"Execution plan: {plan}")

        self.post_message(
            run_id=run_id,
            msg_type="ORCHESTRATOR_PLAN",
            payload={
                "plan": remaining,
                "current_status": status,
                "is_resume": is_resume,
                "topic": topic,
            },
        )

    def _get_remaining_agents(self, status: str) -> list[str]:
        """Return the ordered list of agents still to run."""
        full_order = ["trend_scout", "narrator", "production", "publisher"]
        agent_name = _STATUS_TO_AGENT.get(status)
        if agent_name is None:
            return []
        try:
            start_idx = full_order.index(agent_name)
            return full_order[start_idx:]
        except ValueError:
            return []

    def _dispatch(
        self, agent_name: str, run_id: str, ctx: Dict[str, Any]
    ) -> AgentResult:
        """Invoke a specialist agent with retry logic."""
        agent = self._agents[agent_name]
        max_retries = 2
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                self.log(
                    f"Invoking {agent_name.upper()} "
                    f"(attempt {attempt}/{max_retries})..."
                )
                result = agent.run(run_id=run_id, context=ctx)
                return result
            except Exception as e:
                last_error = e
                self.log(
                    f"{agent_name.upper()} raised exception "
                    f"(attempt {attempt}): {e}"
                )
                if attempt < max_retries:
                    wait = 2 ** attempt
                    self.log(f"Waiting {wait}s before retry...")
                    time.sleep(wait)

        return AgentResult(
            success=False,
            reasoning=f"Agent {agent_name} failed after {max_retries} attempts.",
            errors=[str(last_error)],
        )

    def _reflect(self, agent_name: str, result: AgentResult) -> None:
        """Log the agent's reasoning after it completes."""
        status = "✓" if result.success else "✗"
        self.log(
            f"[REFLECT] {agent_name.upper()} {status}: {result.reasoning[:120]}"
        )
        if result.errors:
            self.log(f"[REFLECT] Non-fatal issues: {result.errors}")

    def _advance_status(
        self,
        agent_name: str,
        run_id: str,
        result: AgentResult,
        ctx: Dict[str, Any],
    ) -> str:
        """Update pipeline status after an agent completes and refresh ctx."""
        if agent_name == "trend_scout":
            topic = result.output.get("topic", "")
            # Update the placeholder topic in DB
            self._update_topic(run_id, topic)
            ctx["topic"] = topic
            # Narrator is next — mark as still PENDING (narrator will advance)
            # We use a virtual status to prevent re-running TrendScout on resume
            self.state.update_status(run_id, "TOPIC_FOUND")
            return "TOPIC_FOUND"

        elif agent_name == "narrator":
            scenes = result.output.get("scenes", [])
            self.state.save_scenes(run_id, scenes)
            self.state.update_status(run_id, "NARRATED")
            ctx["scenes"] = scenes
            return "NARRATED"

        elif agent_name == "production":
            image_paths = result.output.get("image_paths", [])
            audio_map = result.output.get("audio_map", {})
            self.state.save_image_paths(run_id, image_paths)
            self.state.save_audio_map(run_id, audio_map)
            self.state.update_status(run_id, "AUDIO_DONE")
            ctx["image_paths"] = image_paths
            ctx["audio_map"] = audio_map
            return "AUDIO_DONE"

        elif agent_name == "publisher":
            final_path = result.output.get("final_path", "")
            if final_path:
                self.state.save_final_path(run_id, final_path)
            self.state.mark_done(run_id)
            return "DONE"

        return self.state.get_run_status(run_id)

    def _update_topic(self, run_id: str, topic: str) -> None:
        """Update the topic field on the pipeline_runs row."""
        import sqlite3
        import config as cfg
        conn = sqlite3.connect(cfg.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pipeline_runs SET topic = ? WHERE run_id = ?",
            (topic, run_id),
        )
        conn.commit()
        conn.close()


# ── Extend status map for TOPIC_FOUND (new intermediate state) ─────────────────

_STATUS_TO_AGENT["TOPIC_FOUND"] = "narrator"
