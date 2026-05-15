# agents/orchestrator.py
"""
OrchestratorAgent — the brain of the multi-agent pipeline.

The Orchestrator is responsible for:
  1. Planning:         Declaring the full execution plan upfront
  2. Routing:          Deciding which agent runs next from pipeline status
  3. Crash Recovery:   Reading blackboard to resume from exact failure point
  4. Reflection:       Logging each agent's reasoning before proceeding
  5. Revision Loop:    Managing the Narrator ↔ Critic feedback cycle
  6. Failure Handling: Retry with exponential backoff; graceful degradation

Full pipeline (Task 2):
  TrendScout → Research → Planner → Narrator → Critic → Production → Publisher
                                        ↑_______________|
                                          revision loop

Status → Agent mapping:
  PENDING          → TrendScoutAgent
  TOPIC_FOUND      → ResearchAgent
  RESEARCHED       → PlannerAgent
  PLANNED          → NarratorAgent
  AWAITING_CRITIC  → CriticAgent    (Narrator sets this; Critic may send back to PLANNED)
  NARRATED         → ProductionAgent
  AUDIO_DONE       → PublisherAgent
  COMPILED         → PublisherAgent
  DONE             → (terminal)

Note: The revision loop is handled inside _advance_status for the 'critic' case.
When Critic returns REVISE, status reverts to PLANNED and revision_count is
incremented in ctx. The Narrator re-runs with revision_feedback in context.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agents.base import AgentResult, BaseAgent
from agents.trend_scout import TrendScoutAgent
from agents.research import ResearchAgent
from agents.planner import PlannerAgent
from agents.narrator import NarratorAgent
from agents.critic import CriticAgent
from agents.production import ProductionAgent
from agents.publisher import PublisherAgent
from state import PipelineState


# ─── Status → Agent routing table ─────────────────────────────────────────────

_STATUS_TO_AGENT: Dict[str, Optional[str]] = {
    "PENDING":          "trend_scout",
    "TOPIC_FOUND":      "research",
    "RESEARCHED":       "planner",
    "PLANNED":          "narrator",
    "AWAITING_CRITIC":  "critic",
    "NARRATED":         "production",
    "VISUALS_DONE":     "production",   # legacy status — treat as needing production
    "AUDIO_DONE":       "publisher",
    "ANIMATED":         "publisher",
    "COMPILED":         "publisher",
    "DONE":             None,
}

# Ordered agent list used for plan declaration and resume calculation
_FULL_ORDER: List[str] = [
    "trend_scout", "research", "planner",
    "narrator", "critic",
    "production", "publisher",
]


class OrchestratorAgent(BaseAgent):
    """
    Plans, routes, manages the revision loop, and reflects across the pipeline.

    The Orchestrator never does worker tasks itself — it delegates to specialists
    and observes their results. Its unique contributions are the planning layer
    (upfront declaration), the reflection layer (post-agent reasoning logging),
    and the revision loop (autonomous Narrator ↔ Critic iteration).
    """

    name = "orchestrator"

    def __init__(self, state: PipelineState) -> None:
        super().__init__(state)
        self._agents: Dict[str, BaseAgent] = {
            "trend_scout": TrendScoutAgent(state),
            "research":    ResearchAgent(state),
            "planner":     PlannerAgent(state),
            "narrator":    NarratorAgent(state),
            "critic":      CriticAgent(state),
            "production":  ProductionAgent(state),
            "publisher":   PublisherAgent(state),
        }

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(
        self,
        run_id: Optional[str] = None,
        context: Dict[str, Any] = {},
    ) -> AgentResult:
        """Drive the full pipeline for a run (new or resumed)."""
        run_id, is_resume, topic = self._resolve_run(run_id)
        self._declare_plan(run_id, is_resume, topic)

        status = self.state.get_run_status(run_id)
        ctx: Dict[str, Any] = {
            "topic": topic,
            "revision_count": 0,
            "revision_feedback": "",
        }

        while True:
            next_agent_name = _STATUS_TO_AGENT.get(status)

            if next_agent_name is None:
                self.log(f"Run {run_id[:8]} is {status} — pipeline complete.")
                break

            self.log(f"Status={status} → dispatching [{next_agent_name.upper()}]")
            result = self._dispatch(next_agent_name, run_id, ctx)
            self._reflect(next_agent_name, result)

            if not result.success:
                self.log(
                    f"[{next_agent_name.upper()}] failed: {result.errors}"
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

            status = self._advance_status(next_agent_name, run_id, result, ctx)

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

    # ── Status advancement (including revision loop) ──────────────────────────

    def _advance_status(
        self,
        agent_name: str,
        run_id: str,
        result: AgentResult,
        ctx: Dict[str, Any],
    ) -> str:
        """
        Update pipeline state after an agent completes.

        The critic case is the most complex: it either advances to NARRATED
        (approval) or reverts to PLANNED (revision) while incrementing the
        revision counter in ctx.
        """
        if agent_name == "trend_scout":
            topic = result.output.get("topic", "")
            self._update_topic(run_id, topic)
            ctx["topic"] = topic
            self.state.update_status(run_id, "TOPIC_FOUND")
            return "TOPIC_FOUND"

        elif agent_name == "research":
            # Research data lives on the blackboard — nothing to persist in DB
            self.state.update_status(run_id, "RESEARCHED")
            return "RESEARCHED"

        elif agent_name == "planner":
            # ContentBrief lives on the blackboard — nothing to persist in DB
            self.state.update_status(run_id, "PLANNED")
            return "PLANNED"

        elif agent_name == "narrator":
            # Scene draft awaits Critic approval — do not save to DB yet
            ctx["narrator_scenes"] = result.output.get("scenes", [])
            ctx["narrator_topic"] = result.output.get("topic", ctx.get("topic", ""))
            self.state.update_status(run_id, "AWAITING_CRITIC")
            return "AWAITING_CRITIC"

        elif agent_name == "critic":
            decision = result.output.get("decision", "APPROVE")

            if decision == "APPROVE":
                # Persist the approved scenes and advance
                scenes = result.output.get("scenes", ctx.get("narrator_scenes", []))
                self.state.save_scenes(run_id, scenes)
                self.state.update_status(run_id, "NARRATED")
                ctx["scenes"] = scenes
                forced = result.output.get("forced", False)
                revision_count = ctx.get("revision_count", 0)
                self.log(
                    f"[CRITIC APPROVED] scenes saved "
                    f"(revisions={revision_count}, forced={forced})"
                )
                return "NARRATED"

            else:
                # Revision loop: revert to PLANNED, inject feedback into ctx
                ctx["revision_count"] = ctx.get("revision_count", 0) + 1
                ctx["revision_feedback"] = result.output.get("feedback", "")
                self.state.update_status(run_id, "PLANNED")
                self.log(
                    f"[REVISION {ctx['revision_count']}] "
                    f"Re-dispatching Narrator with feedback..."
                )
                return "PLANNED"

        elif agent_name == "production":
            self.state.save_image_paths(run_id, result.output.get("image_paths", []))
            self.state.save_audio_map(run_id, result.output.get("audio_map", {}))
            self.state.update_status(run_id, "AUDIO_DONE")
            return "AUDIO_DONE"

        elif agent_name == "publisher":
            final_path = result.output.get("final_path", "")
            if final_path:
                self.state.save_final_path(run_id, final_path)
            self.state.mark_done(run_id)
            return "DONE"

        return self.state.get_run_status(run_id)

    # ── Supporting methods ────────────────────────────────────────────────────

    def _resolve_run(self, run_id: Optional[str]) -> tuple[str, bool, str]:
        """Resolve the run to use — resume pending or create new."""
        if run_id:
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

        placeholder_run_id = self.state.create_run("TBD")
        self.log(f"New run created: {placeholder_run_id[:8]}")
        return placeholder_run_id, False, ""

    def _declare_plan(self, run_id: str, is_resume: bool, topic: str) -> None:
        """Log the execution plan and post it to the blackboard."""
        status = self.state.get_run_status(run_id)
        remaining = self._get_remaining_agents(status)

        mode = f"RESUMING (status={status}, topic='{topic}')" if is_resume else "STARTING"
        self.log(f"{mode} run {run_id[:8]}")

        plan_str = " → ".join(a.upper() for a in remaining) if remaining else "ALREADY DONE"
        self.log(f"Execution plan: {plan_str}")

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

    def _get_remaining_agents(self, status: str) -> List[str]:
        """Return agents still to run based on current pipeline status."""
        next_agent = _STATUS_TO_AGENT.get(status)
        if next_agent is None:
            return []
        try:
            # For AWAITING_CRITIC, the next agent is critic
            idx = _FULL_ORDER.index(next_agent)
            return _FULL_ORDER[idx:]
        except ValueError:
            return []

    def _dispatch(
        self, agent_name: str, run_id: str, ctx: Dict[str, Any]
    ) -> AgentResult:
        """Invoke a specialist agent with 2-attempt retry and backoff."""
        agent = self._agents[agent_name]

        for attempt in range(1, 3):
            try:
                self.log(
                    f"Invoking {agent_name.upper()} "
                    f"(attempt {attempt}/2)..."
                )
                return agent.run(run_id=run_id, context=dict(ctx))
            except Exception as exc:
                self.log(f"{agent_name.upper()} raised: {exc}")
                if attempt < 2:
                    wait = 2 ** attempt
                    self.log(f"Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    return AgentResult(
                        success=False,
                        reasoning=f"{agent_name} failed after 2 attempts.",
                        errors=[str(exc)],
                    )

        # Unreachable but satisfies type checker
        return AgentResult(success=False, errors=["dispatch exhausted"])

    def _reflect(self, agent_name: str, result: AgentResult) -> None:
        """Log the agent's reasoning after it completes."""
        status = "✓" if result.success else "✗"
        self.log(
            f"[REFLECT] {agent_name.upper()} {status}: "
            f"{result.reasoning[:140]}"
        )
        if result.errors:
            self.log(f"[REFLECT] Non-fatal issues: {result.errors}")

    def _update_topic(self, run_id: str, topic: str) -> None:
        """Update the topic field on pipeline_runs for the TBD placeholder."""
        import sqlite3
        import config as cfg
        conn = sqlite3.connect(cfg.DB_PATH)
        conn.execute(
            "UPDATE pipeline_runs SET topic = ? WHERE run_id = ?",
            (topic, run_id),
        )
        conn.commit()
        conn.close()
