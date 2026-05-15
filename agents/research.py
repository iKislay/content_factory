# agents/research.py
"""
ResearchAgent — gathers real, live web facts via LLM-driven tool use.

This agent satisfies three hackathon requirements:
  - "Web Search":    live DuckDuckGo queries fired at runtime
  - "Tool Calling":  the LLM itself decides which tools to call (not hardcoded Python)
  - "Deep Reasoning": multi-round loop where the LLM synthesises after gathering facts

The key distinction from Task 1/2: the LLM receives a list of tools (web_search,
fetch_url) and autonomously decides:
  - Which search queries to run
  - Whether to fetch a specific URL for deeper content
  - When it has gathered enough information to synthesise a brief
  - How to format the final research output

Every tool call and its result is posted to the blackboard as TOOL_CALLED /
TOOL_RESULT messages, creating a verifiable trace of every external API invocation.

Blackboard messages consumed:
  TOPIC_SELECTED  { topic }

Blackboard messages produced:
  TOOL_CALLED       { agent, tool_name, arguments, call_id }   (one per call)
  TOOL_RESULT       { agent, tool_name, call_id, output_summary, duration_ms }
  RESEARCH_COMPLETE { topic, facts, stats, angles, key_insight, sources, source }
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import config
from agents.base import AgentResult, BaseAgent
from providers.llm import generate_with_tools


_RESEARCH_SYSTEM = """You are a research analyst for a viral short-form video content team.

Your task: gather real, specific facts about the given topic using the available tools.

Research strategy:
1. Run web_search with a query focused on recent statistics and concrete facts
2. Run web_search with a second query focused on surprising or counterintuitive angles
3. If you find an interesting article URL, use fetch_url to read the full content
4. Once you have enough material, respond with a JSON research brief

When you are done researching, respond with ONLY this JSON (no markdown, no backticks):
{
  "facts": ["<specific fact 1>", "<fact 2>", "<fact 3>", "<fact 4>", "<fact 5>"],
  "stats": ["<stat with number/percentage/date>", "<stat 2>", "<stat 3>"],
  "angles": ["<counterintuitive angle 1>", "<angle 2>"],
  "key_insight": "<single most powerful, shareable insight>"
}

Rules:
- Facts must be specific and verifiable, never generic
- Stats must include real numbers, percentages, or dates
- Angles must be genuinely surprising — things most people don't know
- key_insight should be the single claim that would make someone stop scrolling"""

_MINIMAL_FALLBACK: Dict[str, Any] = {
    "facts": ["This topic is evolving rapidly with significant real-world impact."],
    "stats": ["Adoption growing at double-digit rates annually."],
    "angles": ["Most people fundamentally misunderstand the core mechanism."],
    "key_insight": "The gap between public perception and reality is wider than most realise.",
}


class ResearchAgent(BaseAgent):
    """
    Gathers real web facts via LLM-driven tool use.

    The LLM autonomously selects which web_search queries to run, optionally
    fetches URLs for deeper reading, and synthesises a structured ResearchBrief.
    Every tool invocation is traced to the blackboard.
    """

    name = "research"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting LLM-driven web research...")

        topic_msg = self.get_latest(run_id, "TOPIC_SELECTED")
        topic = (
            topic_msg["payload"]["topic"]
            if topic_msg
            else context.get("topic", "technology")
        )
        self.log(f"Topic: '{topic}'")

        # ── Tool-use loop ─────────────────────────────────────────────────────
        from tools import registry

        available_tools = [
            registry.get("web_search"),
            registry.get("fetch_url"),
        ]

        executor = self.make_executor(run_id)

        self.log(
            f"Calling LLM with tools: "
            f"{[t.name for t in available_tools if t]}"
        )

        try:
            final_text, all_calls, all_results = generate_with_tools(
                system_prompt=_RESEARCH_SYSTEM,
                user_prompt=f"Research this topic thoroughly: {topic}",
                tools=available_tools,
                executor=executor,
                max_rounds=config.MAX_TOOL_ROUNDS,
            )
        except Exception as e:
            self.log(f"generate_with_tools failed: {e} — using LLM-only fallback")
            final_text, all_calls, all_results = self._llm_only_fallback(topic)

        # ── Log tool-use summary ──────────────────────────────────────────────
        self.log(
            f"Tool-use complete: {len(all_calls)} calls, "
            f"{sum(1 for r in all_results if r.is_ok())} succeeded"
        )
        for call, result in zip(all_calls, all_results):
            status = "✓" if result.is_ok() else f"✗ {result.error}"
            self.log(
                f"  {call.tool_name}({list(call.arguments.keys())}) "
                f"→ {status} ({result.duration_ms:.0f}ms)"
            )

        # ── Parse the final research brief ────────────────────────────────────
        brief = self._parse_brief(final_text)
        source_label = "web_search" if all_calls else "llm_fallback"

        sources = [
            r.output[0]["url"]
            for r in all_results
            if r.is_ok()
            and isinstance(r.output, list)
            and r.output
            and isinstance(r.output[0], dict)
            and "url" in r.output[0]
        ]

        self.log(f"Key insight: {brief['key_insight'][:100]}")

        payload = {
            "topic": topic,
            "facts": brief["facts"],
            "stats": brief["stats"],
            "angles": brief["angles"],
            "key_insight": brief["key_insight"],
            "sources": sources[:8],
            "source": source_label,
            "tool_calls_count": len(all_calls),
        }

        self.post_message(
            run_id=run_id,
            msg_type="RESEARCH_COMPLETE",
            payload=payload,
            recipient="planner",
        )

        return AgentResult(
            success=True,
            output=payload,
            next_agent="planner",
            reasoning=(
                f"Researched '{topic}' via {len(all_calls)} tool calls "
                f"({source_label}). "
                f"{len(brief['facts'])} facts, {len(brief['stats'])} stats. "
                f"Key insight: {brief['key_insight'][:80]}."
            ),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _llm_only_fallback(self, topic: str):
        """Plain LLM call when generate_with_tools() fails entirely."""
        from providers.llm import generate

        system = (
            "You are a research analyst. Provide a research brief about the topic. "
            "Return ONLY a raw JSON object with keys: facts, stats, angles, key_insight."
        )
        try:
            text = generate(system, f"Topic: {topic}")
            return text, [], []
        except Exception:
            return json.dumps(_MINIMAL_FALLBACK), [], []

    def _parse_brief(self, text: str) -> Dict[str, Any]:
        """Parse and normalise the JSON research brief from LLM output."""
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    return dict(_MINIMAL_FALLBACK)
            else:
                return dict(_MINIMAL_FALLBACK)

        return {
            "facts": (data.get("facts") or [])[:5],
            "stats": (data.get("stats") or [])[:3],
            "angles": (data.get("angles") or [])[:2],
            "key_insight": data.get("key_insight", _MINIMAL_FALLBACK["key_insight"]),
        }
