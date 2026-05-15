# agents/narrator.py
"""
NarratorAgent — scene writer, grounded in research and brief.

After Task 2, the Narrator's responsibility narrows to one focused task:
given a fully-specified ContentBrief (from PlannerAgent) and a ResearchBrief
(from ResearchAgent), write exactly 5 scenes that execute on the plan.

The internal mini-planning step from Task 1 is retired — that cognitive work
now lives in PlannerAgent where it belongs. The Narrator is now a specialist
executor, not a planner.

It also handles revision feedback: if the Orchestrator passes revision_feedback
in context (from a prior CriticAgent cycle), the Narrator injects that feedback
into the scene-writing prompt and re-drafts.

Blackboard messages consumed:
  CONTENT_BRIEF      { chosen_angle, emotional_arc, visual_motif,
                       research_facts, research_stats, key_insight }
  RESEARCH_COMPLETE  { facts, stats, key_insight }
  REVISION_REQUESTED { feedback } (present only during revision cycles)

Blackboard messages produced:
  NARRATIVE_DRAFT  { scenes, topic, attempt }
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.base import AgentResult, BaseAgent
from modules.narrator import _parse_scenes
from providers.llm import generate
from providers.fact_grounding import check_grounding, select_mandatory_fact


_SCENE_WRITE_SYSTEM = """You are a master storyteller creating engaging short-form video content.

Return ONLY a raw JSON array — no markdown, no backticks, no preamble whatsoever.

Generate between 5 and 12 scenes with this exact schema:
{
  "scene_id": int,
  "visual_prompt": str,
  "narration": str,
  "motion_directive": str
}

Rules:
- scene_id 1 narration MUST start with one of: "nobody mentions this",
  "pause for a second", "here's the real truth", "let me save you hours",
  "this may surprise you", "I just figured this out"
- All narrations are SHORT: 1-2 sentences max, punchy, first-person
- Total narration across all scenes should be ~30-60 seconds when spoken (60-150 words)
- visual_prompt: 2-4 word concrete image description, then append:
  ", premium minimalist aesthetic, clean composition, 9:16 vertical frame,
  soft bokeh background, teal-and-orange color grade, photorealistic, 4K"
- motion_directive must be exactly one of: "slow zoom in", "gentle pan right",
  "slow zoom out", "gentle pan left", "static"
- Each scene should serve its designated emotional beat from the arc provided"""


class NarratorAgent(BaseAgent):
    """
    Writes 5 scenes grounded in the ContentBrief and ResearchBrief.

    On revision cycles, the Critic's feedback is injected into the prompt
    alongside the original brief, so the Narrator understands exactly what
    to fix rather than guessing.
    """

    name = "narrator"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        revision_count: int = context.get("revision_count", 0)
        revision_feedback: str = context.get("revision_feedback", "")
        is_revision = revision_count > 0

        self.log(
            f"Writing scenes "
            f"({'revision ' + str(revision_count) if is_revision else 'first draft'})..."
        )

        # ── Load context from blackboard ──────────────────────────────────────
        brief_msg = self.get_latest(run_id, "CONTENT_BRIEF")
        research_msg = self.get_latest(run_id, "RESEARCH_COMPLETE")
        topic_msg = self.get_latest(run_id, "TOPIC_SELECTED")

        topic: str = context.get("topic", "technology")
        if brief_msg:
            topic = brief_msg["payload"].get("topic", topic)
        elif topic_msg:
            topic = topic_msg["payload"].get("topic", topic)

        brief: Dict = brief_msg["payload"] if brief_msg else {}
        research: Dict = research_msg["payload"] if research_msg else {}

        # If revision, also read feedback from blackboard as a fallback
        if is_revision and not revision_feedback:
            rev_msg = self.get_latest(run_id, "REVISION_REQUESTED")
            if rev_msg:
                revision_feedback = rev_msg["payload"].get("feedback", "")

        self.log(f"Topic: '{topic}'")
        if is_revision:
            self.log(f"Revision feedback: {revision_feedback[:120]}")

        from modules.personas import get_persona
        persona_name = context.get("persona", "The Analyst")
        persona_data = get_persona(persona_name)
        persona_inst = persona_data.get("narrator_instruction", "")

        # ── Build prompt and write scenes ─────────────────────────────────────
        user_prompt = self._build_prompt(topic, brief, research, revision_feedback)
        scenes = self._write_scenes(user_prompt, persona_inst)

        # ── Grounding check ───────────────────────────────────────────────────
        facts = research.get("facts") or brief.get("research_facts", [])
        stats = research.get("stats") or brief.get("research_stats", [])
        grounding = check_grounding(scenes, facts, stats)
        self.log(str(grounding))

        # If first draft has zero grounding, try once more with a stronger directive
        if not grounding.is_grounded and not is_revision:
            self.log(
                "No research facts grounded in first draft — "
                "retrying with stronger grounding directive..."
            )
            stronger_prompt = self._build_prompt(
                topic, brief, research, revision_feedback,
                force_grounding=True,
                mandatory_fact=grounding.mandatory_fact,
            )
            scenes2 = self._write_scenes(stronger_prompt, persona_inst)
            grounding2 = check_grounding(scenes2, facts, stats)
            if grounding2.is_grounded or (5 <= len(scenes2) <= 12):
                scenes = scenes2
                grounding = grounding2
                self.log(f"Grounding after retry: {grounding}")

        for s in scenes:
            self.log(
                f"  Scene {s['scene_id']} [{s['motion_directive']}]: "
                f"'{s['narration'][:70]}...'"
            )

        self.post_message(
            run_id=run_id,
            msg_type="NARRATIVE_DRAFT",
            payload={
                "scenes": scenes,
                "topic": topic,
                "attempt": revision_count,
                "grounding": grounding.to_dict(),
            },
            recipient="critic",
        )

        return AgentResult(
            success=True,
            output={"scenes": scenes, "topic": topic},
            next_agent="critic",
            reasoning=(
                f"Wrote {len(scenes)} scenes (attempt {revision_count}). "
                f"Grounding: {grounding.grounding_score:.2f} "
                f"({len(grounding.grounded_facts)} facts referenced). "
                f"Grounded in {'ContentBrief + research' if brief else 'topic only'}."
            ),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_prompt(
        self,
        topic: str,
        brief: Dict[str, Any],
        research: Dict[str, Any],
        revision_feedback: str,
        force_grounding: bool = False,
        mandatory_fact: str = "",
    ) -> str:
        """Construct a rich, grounded scene-writing prompt."""
        parts = [f"Write 5 scenes for a short video about: {topic}\n"]

        if brief.get("chosen_angle"):
            parts.append(f"Chosen angle: {brief['chosen_angle']}")

        if brief.get("visual_motif"):
            parts.append(f"Visual motif: {brief['visual_motif']}")

        if brief.get("emotional_arc"):
            arc_lines = [
                f"  Scene {b['beat']} ({b['label']}): {b['emotional_goal']}"
                for b in brief["emotional_arc"]
            ]
            parts.append("Emotional arc:\n" + "\n".join(arc_lines))

        facts = research.get("facts") or brief.get("research_facts", [])
        stats = research.get("stats") or brief.get("research_stats", [])
        if facts:
            parts.append(
                "Ground your narration in these REAL, LIVE-RESEARCHED facts:\n"
                + "\n".join(f"  • {f}" for f in facts[:4])
            )
        if stats:
            parts.append(
                "Incorporate at least one of these statistics:\n"
                + "\n".join(f"  • {s}" for s in stats[:2])
            )

        # News headline injection (Task 4)
        news_headline = research.get("news_headline", "")
        if news_headline:
            parts.append(
                f"Recent development (reference this if relevant): {news_headline}"
            )

        if research.get("key_insight") or brief.get("key_insight"):
            insight = research.get("key_insight") or brief.get("key_insight")
            parts.append(f"Key insight to convey: {insight}")

        # Mandatory fact grounding directive (Task 4)
        effective_mandatory = mandatory_fact or select_mandatory_fact(facts, stats)
        if effective_mandatory:
            directive = (
                "\n⚠ MANDATORY REQUIREMENT: You MUST incorporate this specific "
                "statistic or fact (verbatim or closely paraphrased) somewhere "
                "in your narration. This proves your content is research-grounded:\n"
                f'  "{effective_mandatory}"'
            )
            if force_grounding:
                directive = (
                    "\n⚠⚠ CRITICAL: The previous draft failed to reference any "
                    "researched facts. You MUST include this specific fact in the "
                    "narration of at least one scene — it cannot be omitted:\n"
                    f'  "{effective_mandatory}"'
                )
            parts.append(directive)

        if revision_feedback:
            parts.append(
                f"\n⚠ REVISION INSTRUCTIONS (apply these specifically):\n"
                f"{revision_feedback}"
            )

        return "\n\n".join(parts)

    def _write_scenes(self, user_prompt: str, persona_inst: str = "") -> List[Dict]:
        """Write 5 scenes with up to 3 parse attempts."""
        errors: List[str] = []
        sys_prompt = f"{_SCENE_WRITE_SYSTEM}\n\n[PERSONA DIRECTION: {persona_inst}]" if persona_inst else _SCENE_WRITE_SYSTEM

        for attempt in range(1, 4):
            try:
                raw = generate(sys_prompt, user_prompt)
                scenes = _parse_scenes(raw)
                if 5 <= len(scenes) <= 12:
                    return scenes
                errors.append(f"Attempt {attempt}: got {len(scenes)} scenes")
                self.log(f"  Parse attempt {attempt} got {len(scenes)} scenes — retrying")
            except Exception as e:
                errors.append(f"Attempt {attempt}: {e}")
                self.log(f"  Parse attempt {attempt} failed: {e}")

        raise RuntimeError(f"NarratorAgent failed after 3 attempts: {errors}")
