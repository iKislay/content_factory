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

Your task: find the top 3 best topics to create a video about RIGHT NOW.

Steps:
1. Call get_trending_topic to see what's trending (try region="IN" first)
2. Call web_search with the returned topics to verify they are interesting and have
   good video potential.
3. Based on what you find, decide on the 3 best topics.

When you have chosen your final topics, respond with ONLY this text:
TOPIC 1: <the chosen topic 1>
RATIONALE 1: <one sentence explaining why this topic will perform well>
TOPIC 2: <the chosen topic 2>
RATIONALE 2: <one sentence explaining why this topic will perform well>
TOPIC 3: <the chosen topic 3>
RATIONALE 3: <one sentence explaining why this topic will perform well>

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
        user_provided_topic = context.get("topic")
        
        auto_keywords = ['auto-discover', 'find topic', 'discover', 'trending', 'generate topic']
        is_auto_topic = user_provided_topic and any(kw in user_provided_topic.lower() for kw in auto_keywords)
        
        base_topic = None
        if user_provided_topic and user_provided_topic.strip() and user_provided_topic != "TBD" and not is_auto_topic:
            base_topic = user_provided_topic.strip()
            self.log(f"User provided base topic: '{base_topic}' — finding related angles...")

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
            if base_topic:
                user_prompt = f"Find the top 3 best angles or sub-topics for a viral short video about: '{base_topic}' right now."
            else:
                user_prompt = "Find the top 3 best topics for a viral short video right now."
            
            final_text, all_calls, all_results = generate_with_tools(
                system_prompt=_SCOUT_SYSTEM,
                user_prompt=user_prompt,
                tools=available_tools,
                executor=executor,
                max_rounds=config.MAX_TOOL_ROUNDS,
            )
            topics_data = self._parse_response(final_text)
            topic = topics_data[0]["topic"] if topics_data else "TBD"
            rationale = topics_data[0]["rationale"] if topics_data else ""
        except Exception as e:
            self.log(f"Tool-use failed: {e} — using fallback discovery")
            topic, rationale = self._fallback_topic()
            topics_data = [{"topic": topic, "rationale": rationale}]

        source = "tool_use" if all_calls else "fallback"
        self.log(f"Topics found: {[t['topic'] for t in topics_data]} ({source})")
        
        # Post the first one as selected for now, but we will send all to the orchestrator/UI
        self._post_selected(run_id, topic, rationale, source, "IN", topics=topics_data)

        return AgentResult(
            success=True,
            output={"topic": topic, "rationale": rationale, "topics": topics_data},
            next_agent="research",
            reasoning=f"Found {len(topics_data)} topics via {source}. Primary: '{topic}'",
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _parse_response(self, text: str) -> list[dict[str, str]]:
        """Extract TOPICS and RATIONALES from the LLM's final response."""
        results = []
        current = {}

        for line in text.splitlines():
            line = line.strip()
            if "TOPIC" in line.upper() and ":" in line:
                if "topic" in current:
                    results.append(current)
                    current = {}
                current["topic"] = line.split(":", 1)[1].strip()
            elif "RATIONALE" in line.upper() and ":" in line:
                current["rationale"] = line.split(":", 1)[1].strip()

        if current and "topic" in current:
            results.append(current)

        return results

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
        topics: list = None
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
                "topics": topics or [{"topic": topic, "rationale": rationale}]
            },
            recipient="research",
        )

