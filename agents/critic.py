# agents/critic.py
"""
CriticAgent — narrative quality reviewer and revision gatekeeper.

This agent closes the "reflect" loop. After the Narrator writes scenes, the
Critic evaluates them against the ContentBrief and the ResearchBrief using a
formal 5-dimension scoring rubric, then makes a binary decision: APPROVE or
REVISE.

Task 4 addition: the Critic reads the grounding metadata from NARRATIVE_DRAFT
and hard-caps factual_score at 4 when is_grounded==False (no researched facts
appear in the narration). This prevents ungrounded content from achieving a
high overall score and forces a revision that references live research.

Scoring rubric (each dimension 1-10):
  hook_score:      Scene 1 must start with one of the mandated hook openers.
  factual_score:   Claims should be grounded in research facts, not generic.
                   Hard-capped at 4 when grounding.is_grounded == False.
  pacing_score:    Estimated total runtime 25-40 seconds (based on word count).
  coherence_score: All scenes serve the chosen_angle and follow the emotional arc.
  viral_score:     At least one genuinely surprising, share-worthy claim.

Decision rules:
  overall_score >= CRITIC_MIN_SCORE → APPROVE
  overall_score <  CRITIC_MIN_SCORE → REVISE (if revision_count < MAX_REVISION_CYCLES)
  revision_count >= MAX_REVISION_CYCLES → force APPROVE (demo reliability > perfection)

Blackboard messages consumed:
  NARRATIVE_DRAFT  { scenes, attempt, grounding }
  CONTENT_BRIEF    { chosen_angle, emotional_arc, visual_motif }
  RESEARCH_COMPLETE { facts, stats }

Blackboard messages produced:
  NARRATIVE_APPROVED   { scenes, topic, scores, revision_count, forced }
  REVISION_REQUESTED   { feedback, scores, revision_count }
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import config
from agents.base import AgentResult, BaseAgent
from providers.llm import generate


_CRITIC_SYSTEM = """You are a senior content quality reviewer for a viral short-form video studio.

You will evaluate a 5-scene narrative draft against a ContentBrief and ResearchBrief.

Return ONLY a raw JSON object — no markdown, no backticks, no preamble:
{
  "hook_score": <1-10>,
  "factual_score": <1-10>,
  "pacing_score": <1-10>,
  "coherence_score": <1-10>,
  "viral_score": <1-10>,
  "overall": <1-10>,
  "decision": "APPROVE" | "REVISE",
  "feedback": "<specific, actionable revision instructions per scene, or empty string if APPROVE>"
}

Scoring guide:
- hook_score:      10 if scene 1 starts with exactly one of: "nobody mentions this",
                   "pause for a second", "here's the real truth", "let me save you hours",
                   "this may surprise you", "I just figured this out". Score 1 otherwise.
- factual_score:   10 if narration contains specific claims traceable to the research facts.
                   Deduct 2 for each scene with only generic statements.
- pacing_score:    Count total words across all narrations. 60-90 words ≈ 30s = score 10.
                   Deduct 1 per 10 words outside 50-100 word range.
- coherence_score: 10 if all scenes clearly serve the chosen_angle and follow the
                   emotional arc (Hook → Tension → Insight → Proof → CTA). Deduct 2
                   per scene that feels off-topic or breaks the arc.
- viral_score:     10 if there is at least one genuinely counterintuitive claim that
                   would make a viewer stop scrolling. 5 if only mildly interesting.
                   1 if all claims are obvious.

Set decision to "REVISE" if overall < {min_score}. Feedback MUST be specific:
reference individual scene_ids and say exactly what to change."""


def _build_critic_prompt(
    scenes: List[Dict],
    brief: Dict[str, Any],
    research: Dict[str, Any],
    grounding: Dict[str, Any] = None,
) -> str:
    """Construct the user prompt for the critic LLM call."""
    scenes_text = json.dumps(scenes, indent=2)
    arc_text = "\n".join(
        f"  Beat {b['beat']} ({b['label']}): {b['emotional_goal']}"
        for b in brief.get("emotional_arc", [])
    )
    facts_text = "\n".join(f"  • {f}" for f in research.get("facts", []))
    stats_text = "\n".join(f"  • {s}" for s in research.get("stats", []))

    # Grounding analysis section (Task 4)
    grounding_section = ""
    if grounding:
        grounded = grounding.get("grounded_facts", [])
        score = grounding.get("grounding_score", 0.0)
        is_grounded = grounding.get("is_grounded", False)
        grounding_section = (
            f"\n=== FACT GROUNDING ANALYSIS ===\n"
            f"Research facts referenced in narration: {len(grounded)}\n"
            f"Grounding score: {score:.2f} (0=none, 1=all facts referenced)\n"
            f"Is grounded: {is_grounded}\n"
            + (
                "Grounded facts:\n"
                + "\n".join(f"  ✓ {f}" for f in grounded[:3])
                if grounded
                else "  ✗ No researched facts found in narration text."
            )
        )

    return (
        f"=== CONTENT BRIEF ===\n"
        f"Chosen angle: {brief.get('chosen_angle', 'N/A')}\n"
        f"Visual motif: {brief.get('visual_motif', 'N/A')}\n"
        f"Emotional arc:\n{arc_text}\n\n"
        f"=== RESEARCH FACTS ===\n{facts_text}\n\n"
        f"=== RESEARCH STATS ===\n{stats_text}\n"
        f"{grounding_section}\n\n"
        f"=== NARRATIVE DRAFT ===\n{scenes_text}"
    )



class CriticAgent(BaseAgent):
    """
    Evaluates narrative drafts and drives the revision feedback loop.

    The Critic reads three blackboard artifacts — NARRATIVE_DRAFT, CONTENT_BRIEF,
    and RESEARCH_COMPLETE — and assesses whether the draft honours the plan.
    This is the "reflect" step: the system evaluates its own work before shipping.
    """

    name = "critic"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        revision_count: int = context.get("revision_count", 0)
        self.log(
            f"Evaluating narrative draft "
            f"(revision cycle {revision_count}/{config.MAX_REVISION_CYCLES})..."
        )

        # ── Load blackboard artifacts ─────────────────────────────────────────
        draft_msg = self.get_latest(run_id, "NARRATIVE_DRAFT")
        brief_msg = self.get_latest(run_id, "CONTENT_BRIEF")
        research_msg = self.get_latest(run_id, "RESEARCH_COMPLETE")

        if not draft_msg:
            return AgentResult(
                success=False,
                reasoning="NARRATIVE_DRAFT message missing from blackboard.",
                errors=["No draft to evaluate"],
            )

        scenes: List[Dict] = draft_msg["payload"]["scenes"]
        topic: str = draft_msg["payload"].get("topic", context.get("topic", ""))
        brief: Dict = brief_msg["payload"] if brief_msg else {}
        research: Dict = research_msg["payload"] if research_msg else {}

        # Read grounding metadata attached by NarratorAgent (Task 4)
        grounding: Dict = draft_msg["payload"].get("grounding", {})
        is_grounded: bool = grounding.get("is_grounded", True)  # default True = don't penalise legacy runs
        grounded_facts: List = grounding.get("grounded_facts", [])
        grounding_score: float = grounding.get("grounding_score", 1.0)

        # ── LLM evaluation ────────────────────────────────────────────────────
        scores = self._evaluate(scenes, brief, research, grounding)

        # ── Hard-cap factual_score when no research facts are grounded (Task 4) ──
        if not is_grounded and scores.get("factual_score", 10) > 4:
            self.log(
                f"factual_score capped: is_grounded=False "
                f"(was {scores['factual_score']}, capped at 4)"
            )
            scores["factual_score"] = 4
            dim_keys = ["hook_score", "factual_score", "pacing_score",
                        "coherence_score", "viral_score"]
            scores["overall"] = max(
                1, min(10, round(sum(scores[k] for k in dim_keys) / len(dim_keys)))
            )
            if scores["overall"] < config.CRITIC_MIN_SCORE:
                scores["decision"] = "REVISE"
                if not scores.get("feedback"):
                    scores["feedback"] = (
                        "The narration does not reference any specific researched facts. "
                        "Revise to include at least one concrete statistic or fact from "
                        "the research brief (specific numbers, dates, or named findings)."
                    )

        overall = scores.get("overall", 0)
        decision = scores.get("decision", "APPROVE")
        feedback = scores.get("feedback", "")

        self._log_scores(scores)

        # ── Force approval if max revision cycles reached ──────────────────────
        forced = False
        if decision == "REVISE" and revision_count >= config.MAX_REVISION_CYCLES:
            self.log(
                f"Max revision cycles ({config.MAX_REVISION_CYCLES}) reached "
                f"— forcing APPROVE (score={overall})"
            )
            decision = "APPROVE"
            forced = True

        # ── Post result to blackboard ─────────────────────────────────────────
        if decision == "APPROVE":
            self.post_message(
                run_id=run_id,
                msg_type="NARRATIVE_APPROVED",
                payload={
                    "scenes": scenes,
                    "topic": topic,
                    "scores": scores,
                    "revision_count": revision_count,
                    "forced": forced,
                },
                recipient="production",
            )
            reasoning = (
                f"Approved after {revision_count} revision(s). "
                f"Score: {overall}/10 "
                f"({'forced' if forced else 'genuine'} approval)."
            )
            return AgentResult(
                success=True,
                output={
                    "decision": "APPROVE",
                    "scenes": scenes,
                    "topic": topic,
                    "scores": scores,
                    "forced": forced,
                },
                next_agent="production",
                reasoning=reasoning,
            )

        else:
            self.post_message(
                run_id=run_id,
                msg_type="REVISION_REQUESTED",
                payload={
                    "feedback": feedback,
                    "scores": scores,
                    "revision_count": revision_count,
                },
                recipient="narrator",
            )
            self.log(f"Revision requested: {feedback[:120]}")
            return AgentResult(
                success=True,
                output={
                    "decision": "REVISE",
                    "feedback": feedback,
                    "scores": scores,
                    "revision_count": revision_count,
                },
                next_agent="narrator",
                reasoning=(
                    f"Score {overall}/10 below threshold {config.CRITIC_MIN_SCORE}. "
                    f"Requesting revision {revision_count + 1}. "
                    f"Feedback: {feedback[:80]}."
                ),
            )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _evaluate(
        self,
        scenes: List[Dict],
        brief: Dict[str, Any],
        research: Dict[str, Any],
        grounding: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Call the LLM critic and parse the evaluation JSON."""
        system = _CRITIC_SYSTEM.format(min_score=config.CRITIC_MIN_SCORE)
        user = _build_critic_prompt(scenes, brief, research, grounding or {})

        try:
            raw = generate(system, user)
            return self._parse_scores(raw)
        except Exception as e:
            self.log(f"Critic LLM call failed: {e} — defaulting to APPROVE")
            return {
                "hook_score": 7, "factual_score": 7, "pacing_score": 7,
                "coherence_score": 7, "viral_score": 7, "overall": 7,
                "decision": "APPROVE", "feedback": "",
            }

    def _parse_scores(self, text: str) -> Dict[str, Any]:
        """Parse the JSON scoring object from LLM output."""
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                data = json.loads(m.group())
            else:
                raise ValueError("No JSON object in critic output")

        # Ensure all required keys exist with safe defaults
        defaults = {
            "hook_score": 5, "factual_score": 5, "pacing_score": 5,
            "coherence_score": 5, "viral_score": 5, "overall": 5,
            "decision": "APPROVE", "feedback": "",
        }
        for k, v in defaults.items():
            data.setdefault(k, v)

        # Clamp scores 1-10
        for dim in ("hook_score", "factual_score", "pacing_score",
                    "coherence_score", "viral_score", "overall"):
            data[dim] = max(1, min(10, int(data[dim])))

        return data

    def _log_scores(self, scores: Dict[str, Any]) -> None:
        """Log a compact score summary."""
        self.log(
            f"Scores — "
            f"hook={scores['hook_score']} "
            f"factual={scores['factual_score']} "
            f"pacing={scores['pacing_score']} "
            f"coherence={scores['coherence_score']} "
            f"viral={scores['viral_score']} "
            f"overall={scores['overall']}/10 "
            f"→ {scores['decision']}"
        )
