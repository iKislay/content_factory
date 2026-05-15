# agents/planner.py
"""
PlannerAgent — strategic content planner using 4-step sequential reasoning.

This is the core "decompose and plan" agent. Rather than asking one LLM call
to plan everything at once, PlannerAgent makes 4 sequential calls where each
step's output grounds the next. This mirrors how a real content strategy team
works: audience first, then angle, then arc, then visuals.

Reasoning chain:
  Step 1 — Audience Analysis:  Who is watching? What do they already know?
                                What emotional state are they in?
  Step 2 — Angle Selection:    Given the audience and research, what is the
                                single most counterintuitive take? Why were
                                other angles rejected?
  Step 3 — Emotional Arc:      5-beat arc (Hook/Tension/Insight/Proof/CTA)
                                describing the desired feeling at each scene.
  Step 4 — Visual Motif:       One unifying visual metaphor that ties all 5
                                scenes together and reinforces the angle.

The assembled ContentBrief is the source of truth for both Narrator (writes
the scenes) and Critic (evaluates whether scenes honour the brief).

Blackboard messages consumed:
  RESEARCH_COMPLETE  { facts, stats, angles, key_insight }
  TOPIC_SELECTED     { topic, rationale }

Blackboard messages produced:
  CONTENT_BRIEF  { topic, audience_profile, chosen_angle, rejection_reasoning,
                   emotional_arc, visual_motif, research_facts, research_stats,
                   key_insight }
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from agents.base import AgentResult, BaseAgent
from providers.llm import generate


# ─── Step-specific system prompts ────────────────────────────────────────────

_AUDIENCE_SYSTEM = """You are an audience research expert for a viral short-form video channel.

Given a topic and research brief, describe the ideal viewer for this content.
Write 2-3 sentences covering:
- Who they are (demographics / interests)
- What they already know about the topic (knowledge baseline)
- What emotional state they're in when they encounter this content

Be specific and opinionated. No generic answers like "tech enthusiasts"."""

_ANGLE_SYSTEM = """You are a content strategist choosing the angle for a viral short video.

Given a topic, research brief, and audience profile, choose the SINGLE most
counterintuitive or surprising angle to take.

Return ONLY a raw JSON object — no markdown, no backticks:
{
  "chosen_angle": "<the angle in one clear sentence>",
  "why_this_wins": "<why this angle will outperform others for this audience>",
  "rejected_angles": ["<angle you considered but rejected>", "<another rejected angle>"],
  "rejection_reasoning": "<one sentence on why the rejected angles are weaker>"
}"""

_ARC_SYSTEM = """You are a narrative architect for short-form video.

Design a 5-beat emotional arc for the video. Each beat maps to one scene.

Return ONLY a raw JSON array — no markdown, no backticks:
[
  {"beat": 1, "label": "Hook",    "emotional_goal": "<what should the viewer feel/think at this beat>"},
  {"beat": 2, "label": "Tension", "emotional_goal": "..."},
  {"beat": 3, "label": "Insight", "emotional_goal": "..."},
  {"beat": 4, "label": "Proof",   "emotional_goal": "..."},
  {"beat": 5, "label": "CTA",     "emotional_goal": "..."}
]

Each emotional_goal must be specific to the chosen angle and audience — not generic."""

_MOTIF_SYSTEM = """You are a visual director for a short-form video channel.

Given the topic, angle, and emotional arc, choose ONE visual metaphor or motif
that will tie all 5 scenes together.

Write 2-3 sentences describing:
- What the visual motif is (a specific image, colour palette, setting, or object)
- How it reinforces the chosen angle
- How it evolves across the 5 beats of the arc

Be concrete. "Technology" is not a motif. "A lone circuit board gradually
surrounded by nature" is a motif."""


class PlannerAgent(BaseAgent):
    """
    Produces a structured ContentBrief via 4 sequential reasoning steps.

    Each step's output is fed as grounding context into the next prompt,
    preventing the LLM from contradicting itself across steps and producing
    a coherent, internally-consistent brief.
    """

    name = "planner"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting 4-step content planning...")

        # ── Load context from blackboard ──────────────────────────────────────
        research_msg = self.get_latest(run_id, "RESEARCH_COMPLETE")
        topic_msg = self.get_latest(run_id, "TOPIC_SELECTED")

        topic = (
            research_msg["payload"].get("topic", context.get("topic", "technology"))
            if research_msg
            else context.get("topic", "technology")
        )
        research = research_msg["payload"] if research_msg else {}
        topic_rationale = (
            topic_msg["payload"].get("rationale", "") if topic_msg else ""
        )

        self.log(f"Planning: '{topic}'")
        rc = self._research_context(research)

        # ── Step 1: Audience analysis ─────────────────────────────────────────
        self.log("Step 1/4 — Audience analysis...")
        audience_profile = self._step_audience(topic, rc, topic_rationale)
        self.log(f"  → {audience_profile[:100]}...")

        # ── Step 2: Angle selection ───────────────────────────────────────────
        self.log("Step 2/4 — Angle selection (with rejection reasoning)...")
        angle_data = self._step_angle(topic, rc, audience_profile)
        chosen_angle = angle_data.get("chosen_angle", "")
        rejection_reasoning = angle_data.get("rejection_reasoning", "")
        self.log(f"  → Chosen: {chosen_angle[:100]}")
        for rejected in angle_data.get("rejected_angles", []):
            self.log(f"  ✗ Rejected: {rejected[:80]}")

        # ── Step 3: Emotional arc ─────────────────────────────────────────────
        self.log("Step 3/4 — Emotional arc design...")
        emotional_arc = self._step_arc(topic, rc, audience_profile, chosen_angle)
        arc_summary = " → ".join(b.get("label", "?") for b in emotional_arc)
        self.log(f"  → {arc_summary}")

        # ── Step 4: Visual motif ──────────────────────────────────────────────
        self.log("Step 4/4 — Visual motif selection...")
        visual_motif = self._step_motif(topic, audience_profile, chosen_angle, emotional_arc)
        self.log(f"  → {visual_motif[:100]}")

        # ── Assemble ContentBrief ─────────────────────────────────────────────
        brief: Dict[str, Any] = {
            "topic": topic,
            "audience_profile": audience_profile,
            "chosen_angle": chosen_angle,
            "rejection_reasoning": rejection_reasoning,
            "emotional_arc": emotional_arc,
            "visual_motif": visual_motif,
            "research_facts": research.get("facts", []),
            "research_stats": research.get("stats", []),
            "key_insight": research.get("key_insight", ""),
        }

        self.log("ContentBrief assembled ✓")

        self.post_message(
            run_id=run_id,
            msg_type="CONTENT_BRIEF",
            payload=brief,
            recipient="narrator",
        )

        return AgentResult(
            success=True,
            output=brief,
            next_agent="narrator",
            reasoning=(
                f"4-step plan for '{topic}': "
                f"audience={audience_profile[:50]}... | "
                f"angle={chosen_angle[:50]}... | "
                f"arc={arc_summary} | "
                f"motif={visual_motif[:50]}..."
            ),
        )

    # ── Step implementations ──────────────────────────────────────────────────

    def _step_audience(self, topic: str, research_ctx: str, rationale: str) -> str:
        """Step 1: Generate audience profile."""
        context_note = f"\nTrend rationale: {rationale}" if rationale else ""
        user = (
            f"Topic: {topic}{context_note}\n\n"
            f"Research brief:\n{research_ctx}"
        )
        try:
            return generate(_AUDIENCE_SYSTEM, user).strip()
        except Exception as e:
            self.log(f"  Audience step failed: {e} — using fallback")
            return f"Tech-curious viewers aged 22-35 interested in {topic}."

    def _step_angle(
        self, topic: str, research_ctx: str, audience: str
    ) -> Dict[str, Any]:
        """Step 2: Select the best angle and record rejected alternatives."""
        user = (
            f"Topic: {topic}\n\n"
            f"Audience: {audience}\n\n"
            f"Research brief:\n{research_ctx}"
        )
        try:
            raw = generate(_ANGLE_SYSTEM, user)
            return self._parse_json_object(raw)
        except Exception as e:
            self.log(f"  Angle step failed: {e} — using fallback")
            return {
                "chosen_angle": f"The hidden cost of {topic} that nobody talks about.",
                "why_this_wins": "Scarcity framing drives engagement.",
                "rejected_angles": ["overview of the field"],
                "rejection_reasoning": "Too generic.",
            }

    def _step_arc(
        self, topic: str, research_ctx: str, audience: str, angle: str
    ) -> List[Dict[str, Any]]:
        """Step 3: Design the 5-beat emotional arc."""
        user = (
            f"Topic: {topic}\n"
            f"Audience: {audience}\n"
            f"Chosen angle: {angle}\n\n"
            f"Research context:\n{research_ctx}"
        )
        try:
            raw = generate(_ARC_SYSTEM, user)
            arc = self._parse_json_array(raw)
            if len(arc) == 5:
                return arc
        except Exception as e:
            self.log(f"  Arc step failed: {e} — using default arc")

        return [
            {"beat": 1, "label": "Hook",    "emotional_goal": "Surprise and curiosity"},
            {"beat": 2, "label": "Tension",  "emotional_goal": "Discomfort with current understanding"},
            {"beat": 3, "label": "Insight",  "emotional_goal": "Eureka moment of clarity"},
            {"beat": 4, "label": "Proof",    "emotional_goal": "Confidence in the new understanding"},
            {"beat": 5, "label": "CTA",      "emotional_goal": "Motivation to act or share"},
        ]

    def _step_motif(
        self, topic: str, audience: str, angle: str, arc: List[Dict]
    ) -> str:
        """Step 4: Choose a visual motif that ties all 5 scenes together."""
        arc_summary = ", ".join(
            f"Beat {b['beat']} ({b['label']}): {b['emotional_goal']}" for b in arc
        )
        user = (
            f"Topic: {topic}\n"
            f"Audience: {audience}\n"
            f"Angle: {angle}\n"
            f"Emotional arc: {arc_summary}"
        )
        try:
            return generate(_MOTIF_SYSTEM, user).strip()
        except Exception as e:
            self.log(f"  Motif step failed: {e} — using fallback")
            return (
                "Clean, minimal dark background with a single glowing element that "
                "grows brighter across scenes, symbolising growing understanding."
            )

    # ── Utility ───────────────────────────────────────────────────────────────

    def _research_context(self, research: Dict[str, Any]) -> str:
        """Format a research dict into a compact string for prompt injection."""
        parts = []
        for f in research.get("facts", []):
            parts.append(f"• Fact: {f}")
        for s in research.get("stats", []):
            parts.append(f"• Stat: {s}")
        for a in research.get("angles", []):
            parts.append(f"• Angle to consider: {a}")
        if research.get("key_insight"):
            parts.append(f"• Key insight: {research['key_insight']}")
        return "\n".join(parts) if parts else f"Topic area: {research.get('topic', 'unknown')}"

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        """Parse a JSON object from LLM output, stripping markdown fences."""
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                return json.loads(m.group())
            raise ValueError("No JSON object found in LLM output")

    def _parse_json_array(self, text: str) -> List[Any]:
        """Parse a JSON array from LLM output, stripping markdown fences."""
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\[[\s\S]*\]", text)
            if m:
                return json.loads(m.group())
            raise ValueError("No JSON array found in LLM output")
