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
  7. Progress Logging: Reading PRODUCTION_PROGRESS + PRODUCTION_SUMMARY
                       to surface fan-out timing stats in real time (Task 5)

Full pipeline (Task 2+):
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

try:
    import broadcast
    BROADCAST_AVAILABLE = True
except ImportError:
    BROADCAST_AVAILABLE = False

import logger
_log = logger.get_pipeline_logger("orchestrator")


# ─── Status → Agent routing table ─────────────────────────────────────────────

_STATUS_TO_AGENT: Dict[str, Optional[str]] = {
    "PENDING":                 "trend_scout",
    "TOPIC_AWAITING_APPROVAL": "trend_scout",
    "TOPIC_FOUND":             "research",
    "RESEARCHED":              "planner",
    "PLANNED":                 "narrator",
    "AWAITING_CRITIC":         "critic",
    "SCRIPT_AWAITING_APPROVAL": "critic",      # user can review/edit script
    "NARRATED":                "production",
    "STYLE_AWAITING_APPROVAL": "production",  # user selects visual style
    "VISUALS_DONE":            "production",
    "AUDIO_DONE":              "publisher",
    "ANIMATED":                "publisher",
    "COMPILED":                "publisher",
    "DONE":                   None,
    "CANCELLED":               None,
    "FAILED":                  None,
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
        auto_approve: bool = False,
    ) -> AgentResult:
        """Drive the full pipeline for a run (new or resumed)."""
        run_id, is_resume, topic = self._resolve_run(run_id)
        self._declare_plan(run_id, is_resume, topic)

        status = self.state.get_run_status(run_id)
        ctx: Dict[str, Any] = {
            "topic": topic,
            "revision_count": 0,
            "revision_feedback": "",
            "auto_approve": auto_approve,
        }

        while True:
            current_status = self.state.get_run_status(run_id)
            if BROADCAST_AVAILABLE:
                progress = self._calculate_progress(current_status)
                broadcast.emit_progress_update(run_id, progress, _STATUS_TO_AGENT.get(current_status, "unknown"))

            if current_status in ("CANCELLED", "FAILED"):
                self.log(f"Pipeline {current_status.lower()} — stopping")
                if BROADCAST_AVAILABLE:
                    broadcast.emit_status_change(run_id, current_status, ctx.get("topic", ""))
                return AgentResult(
                    success=False,
                    reasoning=f"Pipeline was {current_status.lower()}",
                    errors=[f"Pipeline cancelled by user" if current_status == "CANCELLED" else "Pipeline failed"],
                )

            if status == "TOPIC_AWAITING_APPROVAL":
                user_input = self._wait_for_topic_approval(run_id)
                if user_input.get("action") == "reject":
                    self.log("Topic rejected by user — re-running TrendScout")
                    # Clear topic from context and database so TrendScout does fresh discovery
                    ctx["topic"] = ""
                    self._update_topic(run_id, "")
                    status = "PENDING"
                    continue
                
                # Check for auto_approve toggle in user input
                if user_input.get("auto_approve") is True:
                    self.log("Auto-approve enabled mid-run by user")
                    ctx["auto_approve"] = True

                selected_topic = user_input.get("selected_topic")
                if selected_topic:
                    ctx["topic"] = selected_topic
                    self._update_topic(run_id, selected_topic)
                    self.post_message(
                        run_id=run_id,
                        msg_type="TOPIC_USER_APPROVED",
                        payload={"topic": selected_topic, "original_topic": ctx.get("topic")},
                    )
                else:
                    self.post_message(
                        run_id=run_id,
                        msg_type="TOPIC_USER_APPROVED",
                        payload={"topic": ctx.get("topic")},
                    )
                status = "TOPIC_FOUND"
                continue

            # Script review decision point (after Critic approves)
            if status == "SCRIPT_AWAITING_APPROVAL":
                user_input = self._wait_for_approval(run_id, "SCRIPT_APPROVAL")
                if user_input.get("action") == "reject":
                    self.log("Script rejected — sending back for revision")
                    ctx["revision_count"] = ctx.get("revision_count", 0) + 1
                    ctx["revision_feedback"] = user_input.get("feedback", "Script needs revision")
                    status = "PLANNED"
                    continue
                
                # User approved - check if they edited the script
                edited_scenes = user_input.get("edited_scenes")
                if edited_scenes:
                    self.state.save_scenes(run_id, edited_scenes)
                    ctx["scenes"] = edited_scenes
                    self.log("Script edited by user")
                
                self.post_message(run_id=run_id, msg_type="SCRIPT_APPROVED", payload={})
                status = "NARRATED"
                continue

            # Visual style decision point (before Production)
            if status == "STYLE_AWAITING_APPROVAL":
                user_input = self._wait_for_approval(run_id, "STYLE_APPROVAL")
                selected_style = user_input.get("selected_style", "minimalist")
                ctx["visual_style"] = selected_style
                self.post_message(
                    run_id=run_id,
                    msg_type="VISUAL_STYLE_SELECTED",
                    payload={"style": selected_style}
                )
                self.log(f"Visual style selected: {selected_style}")
                status = "NARRATED"
                continue

            next_agent_name = _STATUS_TO_AGENT.get(status)

            if next_agent_name is None:
                self.log(f"Run {run_id[:8]} is {status} — pipeline complete.")
                break

            self.log(f"Status={status} → dispatching [{next_agent_name.upper()}]")
            result = self._dispatch(next_agent_name, run_id, ctx)
            
            # Log agent-to-agent handoff
            self._log_agent_handoff(run_id, status, next_agent_name, result, ctx)
            
            self._reflect(next_agent_name, result)

            if not result.success:
                self.log(
                    f"[{next_agent_name.upper()}] failed: {result.errors}"
                )
                self.state.update_status(run_id, "FAILED")
                self.post_message(
                    run_id=run_id,
                    msg_type="AGENT_FAILED",
                    payload={
                        "agent": next_agent_name,
                        "errors": result.errors,
                        "reasoning": result.reasoning,
                    },
                )
                return AgentResult(
                    success=False,
                    output=result.output,
                    reasoning=result.reasoning,
                    errors=result.errors,
                )

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

        if BROADCAST_AVAILABLE:
            broadcast.emit_step_complete(run_id, "pipeline", "completed", "Pipeline completed successfully!")
            broadcast.emit_progress_update(run_id, 100, "completed", f"Video saved to: {final_path}")
            broadcast.emit_status_change(run_id, "DONE", ctx.get("topic", ""))

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
            topics = result.output.get("topics", [{"topic": topic, "rationale": result.output.get("rationale", "")}])
            self._update_topic(run_id, topic)
            ctx["topic"] = topic
            auto_approve = ctx.get("auto_approve", False)
            if not auto_approve:
                self.state.update_status(run_id, "TOPIC_AWAITING_APPROVAL")
                self.post_message(
                    run_id=run_id,
                    msg_type="TOPIC_AWAITING_APPROVAL",
                    payload={
                        "topic": topic, 
                        "topics": topics,
                        "rationale": result.output.get("rationale", "")
                    },
                )
                return "TOPIC_AWAITING_APPROVAL"
            self.post_message(
                run_id=run_id,
                msg_type="TOPIC_AUTO_APPROVED",
                payload={"topic": topic, "rationale": result.output.get("rationale", "")},
            )
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
                scenes = result.output.get("scenes", ctx.get("narrator_scenes", []))
                self.state.save_scenes(run_id, scenes)
                ctx["scenes"] = scenes
                forced = result.output.get("forced", False)
                revision_count = ctx.get("revision_count", 0)
                
                auto_approve = ctx.get("auto_approve", False)
                
                # Post the approved scenes for UI to display
                self.post_message(
                    run_id=run_id,
                    msg_type="NARRATIVE_APPROVED",
                    payload={"scenes": scenes, "topic": ctx.get("topic", "")},
                )
                
                if auto_approve:
                    self.log(f"[CRITIC APPROVED] scenes saved (auto-approve, revisions={revision_count}, forced={forced})")
                    self.state.update_status(run_id, "NARRATED")
                    return "NARRATED"
                
                self.log(f"[CRITIC APPROVED] waiting for script review (revisions={revision_count}, forced={forced})")
                self.state.update_status(run_id, "SCRIPT_AWAITING_APPROVAL")
                self.post_message(
                    run_id=run_id,
                    msg_type="SCRIPT_AWAITING_APPROVAL",
                    payload={"scenes": scenes, "topic": ctx.get("topic", "")},
                )
                return "SCRIPT_AWAITING_APPROVAL"

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
            # Read from PRODUCTION_SUMMARY (Task 5) with backward-compat fallback
            summary_msg = self.state.get_latest_message(run_id, "PRODUCTION_SUMMARY")
            if summary_msg:
                payload = summary_msg["payload"]
                self._log_production_summary(payload)
                self.state.save_image_paths(run_id, payload.get("image_paths", []))
                self.state.save_audio_map(run_id, payload.get("audio_map", {}))
            else:
                # Backward compat: PRODUCTION_SUMMARY not found, use agent result
                self.state.save_image_paths(run_id, result.output.get("image_paths", []))
                self.state.save_audio_map(run_id, result.output.get("audio_map", {}))
            
            auto_approve = ctx.get("auto_approve", False)
            
            if auto_approve:
                self.state.update_status(run_id, "AUDIO_DONE")
                return "AUDIO_DONE"
            
            # Pause for visual style selection
            scenes = self.state.get_scenes(run_id)
            self.state.update_status(run_id, "STYLE_AWAITING_APPROVAL")
            self.post_message(
                run_id=run_id,
                msg_type="STYLE_AWAITING_APPROVAL",
                payload={"scenes": scenes, "topic": ctx.get("topic", "")},
            )
            return "STYLE_AWAITING_APPROVAL"

        elif agent_name == "publisher":
            final_path = result.output.get("final_path", "")
            if final_path:
                self.state.save_final_path(run_id, final_path)
            self.state.mark_done(run_id)
            return "DONE"

        return self.state.get_run_status(run_id)

    # ── Supporting methods ────────────────────────────────────────────────────

    def _calculate_progress(self, status: str) -> int:
        """Calculate pipeline progress percentage based on current status."""
        progress_map = {
            "PENDING": 0,
            "TOPIC_AWAITING_APPROVAL": 10,
            "TOPIC_FOUND": 15,
            "RESEARCHED": 30,
            "PLANNED": 45,
            "AWAITING_CRITIC": 55,
            "NARRATED": 65,
            "VISUALS_DONE": 75,
            "AUDIO_DONE": 85,
            "ANIMATED": 90,
            "COMPILED": 95,
            "DONE": 100,
            "CANCELLED": 0,
            "FAILED": 0,
        }
        return progress_map.get(status, 0)

    def _resolve_run(self, run_id: Optional[str]) -> tuple[str, bool, str]:
        """Resolve the run to use — resume pending or create new."""
        if run_id:
            # Read topic directly from the DB — TOPIC_SELECTED message may not
            # exist yet on brand-new runs, causing topic="" which bypasses the
            # user-topic guard in TrendScoutAgent and triggers LLM discovery.
            import sqlite3
            import config as cfg
            conn = sqlite3.connect(cfg.DB_PATH)
            row = conn.execute(
                "SELECT topic FROM pipeline_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            conn.close()
            db_topic = (row[0] or "").strip() if row else ""

            # Fallback: if DB topic is blank/TBD, check the blackboard message
            if not db_topic or db_topic == "TBD":
                topic_msg = self.state.get_latest_message(run_id, "TOPIC_SELECTED")
                db_topic = topic_msg["payload"]["topic"] if topic_msg else db_topic

            return run_id, True, db_topic

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

        if BROADCAST_AVAILABLE:
            activity_messages = {
                "trend_scout": "Searching Google Trends for trending topics...",
                "research": "Researching topic and gathering facts...",
                "planner": "Determining content strategy and scene structure...",
                "narrator": "Writing script and narration for each scene...",
                "critic": "Reviewing script for quality and accuracy...",
                "production": "Generating images and audio in parallel...",
                "publisher": "Compiling final video...",
            }
            broadcast.emit_agent_activity(
                run_id, agent_name, "started", 
                {"message": activity_messages.get(agent_name, f"Starting {agent_name}...")}
            )

        for attempt in range(1, 3):
            try:
                self.log(
                    f"Invoking {agent_name.upper()} "
                    f"(attempt {attempt}/2)..."
                )
                result = agent.run(run_id=run_id, context=dict(ctx))

                if BROADCAST_AVAILABLE:
                    status_map = {
                        "trend_scout": "topic_found",
                        "research": "researched",
                        "planner": "planned",
                        "narrator": "narrated",
                        "critic": "critic_reviewed",
                        "production": "production_done",
                        "publisher": "published",
                    }
                    broadcast.emit_step_complete(
                        run_id, agent_name, status_map.get(agent_name, "completed"),
                        f"{agent_name.capitalize()} completed successfully" if result.success else f"{agent_name.capitalize()} failed"
                    )

                return result
            except Exception as exc:
                self.log(f"{agent_name.upper()} raised: {exc}")
                if attempt < 2:
                    wait = 2 ** attempt
                    self.log(f"Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    if BROADCAST_AVAILABLE:
                        broadcast.emit_step_complete(
                            run_id, agent_name, "failed",
                            f"{agent_name.capitalize()} failed after 2 attempts: {exc}"
                        )
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

    def _log_agent_handoff(
        self, 
        run_id: str, 
        from_status: str, 
        to_agent: str, 
        result: AgentResult,
        ctx: Dict[str, Any]
    ) -> None:
        """
        Log agent-to-agent handoff with payload details.
        
        This creates a traceable record of what data was passed
        between agents in the pipeline.
        """
        from_status_map = {
            "PENDING": "orchestrator",
            "TOPIC_FOUND": "trend_scout",
            "RESEARCHED": "research",
            "PLANNED": "planner",
            "NARRATED": "narrator",
            "AWAITING_CRITIC": "critic",
            "VISUALS_DONE": "production",
            "AUDIO_DONE": "production",
            "ANIMATED": "publisher",
            "COMPILED": "publisher",
        }
        
        from_agent = from_status_map.get(from_status, "unknown")
        
        payload = {
            "topic": ctx.get("topic", ""),
            "agent_result_success": result.success,
            "agent_output_keys": list(result.output.keys()) if result.output else [],
        }
        
        if result.output:
            if "scenes" in result.output:
                payload["scenes_count"] = len(result.output.get("scenes", []))
            if "quality" in result.output:
                payload["quality_score"] = result.output.get("quality", {}).get("score")
            if "final_path" in result.output:
                payload["has_video_output"] = True
                
        metadata = {
            "from_status": from_status,
            "to_agent": to_agent,
            "reasoning": result.reasoning[:200] if result.reasoning else "",
        }
        
        self.state.log_handoff(
            run_id=run_id,
            from_agent=from_agent,
            to_agent=to_agent,
            payload=payload,
            metadata=metadata
        )
        
        self.log(f"[HANDOFF] {from_agent} → {to_agent}: {payload.get('topic', 'N/A')}")

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

    def _wait_for_topic_approval(self, run_id: str) -> dict:
        """Poll for user input on topic approval."""
        return self._wait_for_approval(run_id, "topic")

    def _wait_for_approval(self, run_id: str, approval_type: str) -> dict:
        """Generic polling for any approval type."""
        import time
        max_wait = 600
        poll_interval = 2
        elapsed = 0
        while elapsed < max_wait:
            current_status = self.state.get_run_status(run_id)
            if current_status in ("CANCELLED", "FAILED"):
                return {"action": "cancel"}
            user_msg = self.state.get_latest_message(run_id, "USER_INPUT")
            if user_msg:
                payload = user_msg.get("payload", {})
                action = payload.get("action", "")
                if action in ("approve", "reject"):
                    return payload
            time.sleep(poll_interval)
            elapsed += poll_interval
        return {"action": "approve"}

    def _log_production_summary(self, payload: dict) -> None:
        """
        Log a human-readable summary of the production fan-out.

        Surfaces the key Task 5 metrics — wall time, concurrency proof
        (image/audio tasks completing in interleaved order), fastest and
        slowest task details.
        """
        total = payload.get("total_tasks", 0)
        done = payload.get("completed_tasks", 0)
        failed = payload.get("failed_tasks", 0)
        wall_ms = payload.get("wall_time_ms", 0.0)
        fastest = payload.get("fastest_task") or {}
        slowest = payload.get("slowest_task") or {}

        self.log(
            f"[PRODUCTION SUMMARY] "
            f"{done}/{total} tasks complete, {failed} failed | "
            f"wall={wall_ms:.0f}ms"
        )
        if fastest:
            self.log(
                f"  Fastest: {fastest.get('task_id')} "
                f"({fastest.get('duration_ms', 0):.0f}ms) | "
                f"Slowest: {slowest.get('task_id')} "
                f"({slowest.get('duration_ms', 0):.0f}ms)"
            )

        # Log task_details to show image/audio interleaving (concurrency proof)
        details = payload.get("task_details", [])
        if details:
            self.log("  Task timeline (sorted by task_id):")
            for t in sorted(details, key=lambda x: x.get("duration_ms", 0)):
                status_icon = "✓" if t["status"] == "DONE" else "✗"
                self.log(
                    f"    {status_icon} {t['task_id']:<10} "
                    f"{t.get('duration_ms', 0):>7.0f}ms "
                    f"[{t['asset_type']}]"
                )
