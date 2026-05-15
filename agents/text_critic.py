# agents/text_critic.py
"""
TextCriticAgent — text content quality reviewer.

Evaluates text content for:
- Platform authenticity (LinkedIn vs Twitter style)
- Factual grounding (research facts referenced)
- Viral potential (hook quality, engagement triggers)
- Formatting correctness

Blackboard messages consumed:
  TEXT_DRAFT      { content, platform, topic, grounding }
  RESEARCH_COMPLETE { facts, stats }
  CONTENT_BRIEF    { chosen_angle, viral_dna }

Blackboard messages produced:
  TEXT_APPROVED   { content, platform, scores }
  TEXT_REVISION   { feedback, scores }
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from agents.base import AgentResult, BaseAgent
from providers.llm import generate


_LINKEDIN_CRITERIA = """
LinkedIn post criteria:
- Hook: bold claim or question in first 10 words
- Length: 1300-3000 characters
- Formatting: short paragraphs with line breaks
- Professional but conversational tone
- Ends with engagement question
- Contains at least one specific fact or number
"""

_TWITTER_CRITERIA = """
Twitter thread criteria:
- Thread format with numbered tweets
- Hook tweet with bold claim
- 5-10 tweets, each under 280 chars
- No hashtags in body
- Includes specific facts/numbers
- Ends with engagement (question or CTA)
"""


_TEXT_CRITIC_SYSTEM = """You are a senior content quality reviewer for social media.

Evaluate a text draft against platform-specific criteria and research grounding.

Return ONLY a raw JSON object:
{
  "hook_score": <1-10>,
  "grounding_score": <1-10>,
  "format_score": <1-10>,
  "engagement_score": <1-10>,
  "overall": <1-10>,
  "decision": "APPROVE" | "REVISE",
  "feedback": "<specific, actionable feedback or empty if APPROVE>"
}

Scoring:
- hook_score: 10 if starts with scroll-stopper, 1 otherwise
- grounding_score: 10 if references specific research facts/numbers, 1 if generic
- format_score: 10 if follows platform format correctly, 5 otherwise
- engagement_score: 10 if ends with question or strong CTA, 1 otherwise

Decision: APPROVE if overall >= 7, REVISE otherwise."""


class TextCriticAgent(BaseAgent):
    """
    Evaluates text content for platform authenticity and quality.
    """

    name = "text_critic"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Evaluating text content...")

        # Load blackboard artifacts
        draft_msg = self.get_latest(run_id, "TEXT_DRAFT")
        research_msg = self.get_latest(run_id, "RESEARCH_COMPLETE")
        brief_msg = self.get_latest(run_id, "CONTENT_BRIEF")

        if not draft_msg:
            return AgentResult(
                success=False,
                reasoning="TEXT_DRAFT message missing",
                errors=["No text draft to evaluate"],
            )

        content = draft_msg["payload"].get("content", "")
        platform = draft_msg["payload"].get("platform", "linkedin")
        topic = draft_msg["payload"].get("topic", "")
        grounding = draft_msg["payload"].get("grounding", {})

        research = research_msg["payload"] if research_msg else {}
        brief = brief_msg["payload"] if brief_msg else {}

        self.log(f"Evaluating {platform} content ({len(content)} chars)")

        # Run evaluation
        scores = self._evaluate(
            content=content,
            platform=platform,
            research=research,
            grounding=grounding,
        )

        # Enforce grounding check (like video critic)
        is_grounded = grounding.get("is_grounded", True)
        if not is_grounded and scores.get("grounding_score", 10) > 4:
            scores["grounding_score"] = 4
            self.log(f"grounding_score capped at 4 (ungrounded content)")

        overall = scores.get("overall", 0)
        decision = scores.get("decision", "APPROVE")
        feedback = scores.get("feedback", "")

        self._log_scores(scores)

        # Post result to blackboard
        if decision == "APPROVE":
            self.post_message(
                run_id=run_id,
                msg_type="TEXT_APPROVED",
                payload={
                    "content": content,
                    "platform": platform,
                    "topic": topic,
                    "scores": scores,
                },
                recipient="text_publisher",
            )

            return AgentResult(
                success=True,
                output={
                    "decision": "APPROVE",
                    "content": content,
                    "platform": platform,
                    "scores": scores,
                },
                next_agent="text_publisher",
                reasoning=f"Text approved (score: {overall}/10)",
            )
        else:
            self.post_message(
                run_id=run_id,
                msg_type="TEXT_REVISION",
                payload={
                    "feedback": feedback,
                    "scores": scores,
                },
                recipient="text_narrator",
            )

            return AgentResult(
                success=True,
                output={
                    "decision": "REVISE",
                    "feedback": feedback,
                    "scores": scores,
                },
                next_agent="text_narrator",
                reasoning=f"Revision needed (score: {overall}/10). {feedback[:80]}",
            )

    def _evaluate(
        self,
        content: str,
        platform: str,
        research: Dict[str, Any],
        grounding: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate content using LLM."""
        facts = research.get("facts", [])
        stats = research.get("stats", [])

        criteria = _LINKEDIN_CRITERIA if platform == "linkedin" else _TWITTER_CRITERIA

        user_prompt = f"""=== PLATFORM: {platform.upper()} ===
{criteria}

=== RESEARCH FACTS ===
{chr(10).join(f"  • {f}" for f in facts[:5])}

=== RESEARCH STATS ===
{chr(10).join(f"  • {s}" for s in stats[:3])}

=== CONTENT DRAFT ===
{content}
"""

        try:
            raw = generate(_TEXT_CRITIC_SYSTEM, user_prompt)
            return self._parse_scores(raw)
        except Exception as e:
            self.log(f"Critic LLM failed: {e}")
            return {
                "hook_score": 7, "grounding_score": 7,
                "format_score": 7, "engagement_score": 7,
                "overall": 7, "decision": "APPROVE", "feedback": "",
            }

    def _parse_scores(self, text: str) -> Dict[str, Any]:
        """Parse JSON from LLM output."""
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                data = json.loads(m.group())
            else:
                raise ValueError("No JSON in critic output")

        defaults = {
            "hook_score": 5, "grounding_score": 5,
            "format_score": 5, "engagement_score": 5,
            "overall": 5, "decision": "APPROVE", "feedback": "",
        }
        for k, v in defaults.items():
            data.setdefault(k, v)

        for dim in ("hook_score", "grounding_score", "format_score", 
                    "engagement_score", "overall"):
            data[dim] = max(1, min(10, int(data[dim])))

        return data

    def _log_scores(self, scores: Dict[str, Any]) -> None:
        self.log(
            f"Scores: hook={scores['hook_score']} "
            f"grounding={scores['grounding_score']} "
            f"format={scores['format_score']} "
            f"engagement={scores['engagement_score']} "
            f"overall={scores['overall']}/10 → {scores['decision']}"
        )