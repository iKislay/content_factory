# agents/narrator.py
"""
NarratorAgent — deep-reasoning script writer.

This agent uses a two-step LLM process to satisfy the "decompose, plan,
and reflect" requirement:

  Step 1 — Scene Plan:
    Ask the LLM to reason about the topic: what angle to take, what the
    emotional arc should be, which facts are most surprising/viral. The
    output is a free-form strategic plan (not yet scenes).

  Step 2 — Scene Writing:
    Feed the strategic plan back as context and ask the LLM to write
    the actual 5 structured scenes. This two-pass approach yields
    significantly better scene quality than a single-shot prompt.

Blackboard messages consumed:
  TOPIC_SELECTED  { topic, rationale }

Blackboard messages produced:
  SCENE_PLAN      { plan_text }
  NARRATIVE_READY { scenes: List[dict] }
"""

from __future__ import annotations

from typing import Any, Dict, List

from agents.base import AgentResult, BaseAgent
from modules.narrator import _parse_scenes
from providers.llm import generate, LLMError
from state import PipelineState


_SCENE_PLAN_SYSTEM = """You are a senior content strategist for a viral short-form video channel.

Your job is to PLAN (not write) a 5-scene video about the given topic.

Think deeply and answer:
1. What is the single most surprising/counterintuitive angle on this topic?
2. What emotional journey should the viewer take across 5 scenes?
3. What are the 3 most compelling facts or stats about this topic?
4. What visual metaphor or motif would tie all 5 scenes together?
5. What call-to-action or takeaway should scene 5 leave the viewer with?

Write your plan in plain text, 150-200 words. Be specific and opinionated."""

_SCENE_WRITE_SYSTEM = """You are a master storyteller creating engaging short-form video content.

Return ONLY a raw JSON array, no markdown, no backticks, no preamble whatsoever.

Generate exactly 5 scenes with this exact schema:
{
  "scene_id": int,
  "visual_prompt": str,
  "narration": str,
  "motion_directive": str
}

Rules:
- scene_id 1 narration MUST start with one of: "nobody mentions this", "pause for a second", "here's the real truth", "let me save you hours", "this may surprise you", "I just figured this out"
- All narrations are SHORT: 1-2 sentences max, punchy, first-person
- Total narration across all 5 scenes should be ~30 seconds when spoken
- visual_prompt: Create a brief visual description for an image (2-4 words max), then append ", premium minimalist aesthetic, clean composition, 9:16 vertical frame, soft bokeh background, teal-and-orange color grade, photorealistic, 4K"
- motion_directive must be one of: "slow zoom in", "gentle pan right", "slow zoom out", "gentle pan left", "static"

IMPORTANT: Do NOT include the words "STYLE_LOCK" in your response. Just create the visual prompts directly with the style appended."""


class NarratorAgent(BaseAgent):
    """
    Writes the 5-scene video script using a two-step reasoning process.

    Step 1 generates a strategic content plan (angle, arc, facts, motif).
    Step 2 uses that plan as rich context to write the actual scene JSON.
    This mirrors how a real content team works: strategy first, execution second.
    """

    name = "narrator"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting narrative generation (2-step reasoning)...")

        # Read topic from blackboard (prefer blackboard over context dict
        # so that even on resume, we get the original rationale as context)
        topic_msg = self.get_latest(run_id, "TOPIC_SELECTED")
        if topic_msg:
            topic = topic_msg["payload"]["topic"]
            topic_rationale = topic_msg["payload"].get("rationale", "")
        else:
            topic = context.get("topic", "technology trends")
            topic_rationale = ""

        self.log(f"Topic: '{topic}'")

        # ── Step 1: Strategic scene plan ─────────────────────────────────────
        self.log("Step 1/2 — Drafting strategic content plan...")
        plan_text = self._generate_plan(topic, topic_rationale)
        self.log(f"Plan drafted ({len(plan_text.split())} words)")

        self.post_message(
            run_id=run_id,
            msg_type="SCENE_PLAN",
            payload={"plan_text": plan_text, "topic": topic},
        )

        # ── Step 2: Write actual scenes informed by the plan ──────────────────
        self.log("Step 2/2 — Writing 5 scenes from strategic plan...")
        scenes = self._generate_scenes(topic, plan_text)
        self.log(f"Scenes written: {len(scenes)} scenes")

        for s in scenes:
            self.log(
                f"  Scene {s['scene_id']}: [{s['motion_directive']}] "
                f"'{s['narration'][:60]}...'"
            )

        self.post_message(
            run_id=run_id,
            msg_type="NARRATIVE_READY",
            payload={"scenes": scenes, "topic": topic},
            recipient="production",
        )

        return AgentResult(
            success=True,
            output={"scenes": scenes, "topic": topic},
            next_agent="production",
            reasoning=(
                f"Generated {len(scenes)} scenes via 2-step reasoning. "
                f"Plan: {plan_text[:100]}..."
            ),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _generate_plan(self, topic: str, rationale: str) -> str:
        """Step 1: Generate the strategic content plan."""
        context_note = f"\n\nAudience context: {rationale}" if rationale else ""
        user_prompt = f"Plan a viral short-form video about: {topic}{context_note}"

        try:
            return generate(_SCENE_PLAN_SYSTEM, user_prompt)
        except Exception as e:
            self.log(f"Plan generation failed: {e} — using minimal plan")
            return (
                f"Topic: {topic}. Focus on the most surprising aspect. "
                f"Build from hook → education → insight → example → CTA."
            )

    def _generate_scenes(self, topic: str, plan: str) -> List[Dict]:
        """Step 2: Write the 5 structured scenes using the plan as context."""
        user_prompt = (
            f"Using this strategic plan as your guide:\n\n{plan}\n\n"
            f"Now write the 5 scenes for the video about: {topic}"
        )

        errors = []
        for attempt in range(3):
            try:
                raw = generate(_SCENE_WRITE_SYSTEM, user_prompt)
                scenes = _parse_scenes(raw)
                if len(scenes) == 5:
                    return scenes
                errors.append(f"Attempt {attempt+1}: got {len(scenes)} scenes")
            except Exception as e:
                errors.append(f"Attempt {attempt+1}: {e}")
                self.log(f"Scene write attempt {attempt+1} failed: {e}")

        raise RuntimeError(
            f"NarratorAgent failed after 3 attempts: {errors}"
        )
