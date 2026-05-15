# agents/trend_scout.py
"""
TrendScoutAgent — discovers trending topics via LLM-driven tool use.

The LLM receives two tools: get_trending_topic and web_search.
It calls get_trending_topic to find what's hot, then optionally uses web_search
to validate the topic is genuinely interesting and video-worthy before committing.
This is a lightweight but genuine example of the LLM driving tool selection.

Blackboard messages consumed:
  (none — first agent in pipeline)

Blackboard messages produced:
  TOOL_CALLED      { agent, tool_name, arguments, call_id }  (one per call)
  TOOL_RESULT      { agent, tool_name, call_id, output_summary, duration_ms }
  TOPIC_SELECTED   { topic, rationale, source, region }
"""

from __future__ import annotations

import re
from typing import Any, Dict

import config
from agents.base import AgentResult, BaseAgent
from providers.llm import generate_with_tools
from modules.discovery import FALLBACK_TOPICS


_SCOUT_SYSTEM = """You are a trend analyst for a viral short-form video channel.

Your task: find the best topic to create a video about RIGHT NOW.

Steps:
1. Call get_trending_topic to see what's trending (try region="IN" first)
2. Call web_search with the returned topic to verify it's interesting and has
   good video potential (search for recent news or surprising facts about it)
3. Based on what you find, decide: is this topic good for a short video?
   If yes, return the topic. If it's too niche or boring, try get_trending_topic
   with region="US" as a second option.

When you have chosen your final topic, respond with ONLY this text:
TOPIC: <the chosen topic>
RATIONALE: <one sentence explaining why this topic will perform well>

Do not include any other text."""


class TrendScoutAgent(BaseAgent):
    """
    Discovers trending topics with LLM-driven tool use and topic validation.

    The LLM calls get_trending_topic, validates the result via web_search,
    and returns a chosen topic with rationale — rather than blindly accepting
    the first trend returned.
    """

    name = "trend_scout"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        # Resume path — topic already selected in a previous run
        if context.get("topic") and context["topic"] != "TBD":
            topic = context["topic"]
            previous = self.get_latest(run_id, "TOPIC_SELECTED")
            prev_payload = previous.get("payload", {}) if previous else {}
            source = str(prev_payload.get("source") or "resumed")
            region = str(prev_payload.get("region") or "IN")
            self.log(f"Resuming with existing topic: '{topic}'")
            self._post_selected(
                run_id,
                topic,
                "Resumed from previous run.",
                source,
                region,
            )
            return AgentResult(
                success=True,
                output={"topic": topic, "rationale": "Resumed from previous run."},
                next_agent="research",
                reasoning=f"Resumed: topic='{topic}'",
            )

        self.log("Starting LLM-driven topic discovery...")

        from tools import registry

        available_tools = [
            registry.get("get_trending_topic"),
            registry.get("web_search"),
        ]

        executor = self.make_executor(run_id)

        try:
            final_text, all_calls, all_results = generate_with_tools(
                system_prompt=_SCOUT_SYSTEM,
                user_prompt="Find the best topic for a viral short video right now.",
                tools=available_tools,
                executor=executor,
                max_rounds=config.MAX_TOOL_ROUNDS,
            )
            topic, rationale = self._parse_response(final_text)
        except Exception as e:
            self.log(f"Tool-use failed: {e} — using fallback discovery")
            topic, rationale = self._fallback_topic()

        source = "tool_use" if all_calls else "fallback"
        self.log(f"Topic: '{topic}' ({source})")
        self.log(
            f"Tool calls: {len(all_calls)} "
            f"({[c.tool_name for c in all_calls]})"
        )

        self._post_selected(run_id, topic, rationale, source, "IN")

        return AgentResult(
            success=True,
            output={"topic": topic, "rationale": rationale},
            next_agent="research",
            reasoning=f"Selected '{topic}' via {source}. {rationale}",
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _parse_response(self, text: str) -> tuple[str, str]:
        """Extract TOPIC and RATIONALE from the LLM's final response."""
        topic = ""
        rationale = ""

        for line in text.splitlines():
            line = line.strip()
            if line.upper().startswith("TOPIC:"):
                topic = line.split(":", 1)[1].strip()
            elif line.upper().startswith("RATIONALE:"):
                rationale = line.split(":", 1)[1].strip()

        if not topic:
            # Fallback: use the whole response as a topic if short
            topic = text.strip().split("\n")[0][:100]
            rationale = "Selected from LLM response."

        return topic, rationale

    def _fallback_topic(self) -> tuple[str, str]:
        """Return a curated fallback topic when tool-use fails."""
        import time
        idx = int(time.time()) % len(FALLBACK_TOPICS)
        topic = FALLBACK_TOPICS[idx]
        return topic, f"Tool-use unavailable; selected '{topic}' from curated list."

    def _post_selected(
        self,
        run_id: str,
        topic: str,
        rationale: str,
        source: str,
        region: str,
    ) -> None:
        """Post TOPIC_SELECTED to the blackboard."""
        self.post_message(
            run_id=run_id,
            msg_type="TOPIC_SELECTED",
            payload={
                "topic": topic,
                "rationale": rationale,
                "source": source,
                "region": region,
            },
            recipient="research",
        )
