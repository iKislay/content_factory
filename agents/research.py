# agents/research.py
"""
ResearchAgent — gathers real, live web facts before any script is written.

Satisfies two hackathon requirements simultaneously:
  - "Web Search": live DuckDuckGo queries at runtime
  - "Tool Calling": external API calls with real, verifiable side-effects

Process:
  1. Two targeted DuckDuckGo queries (facts/stats + surprising angles)
  2. Raw results formatted and injected into an LLM synthesis prompt
  3. LLM extracts a structured ResearchBrief (facts, stats, angles, insight)
  4. Brief posted to the blackboard for Planner and Narrator to consume

Fallback: If DuckDuckGo is unavailable, uses LLM knowledge-only synthesis
and marks the result source="llm_fallback". The pipeline never fails on
search unavailability.

Blackboard messages consumed:
  TOPIC_SELECTED  { topic }

Blackboard messages produced:
  RESEARCH_COMPLETE  { topic, facts, stats, angles, key_insight, sources, source }
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import config
from agents.base import AgentResult, BaseAgent
from providers import search as search_provider
from providers.llm import generate


_SYNTHESIS_SYSTEM = """You are a research analyst for a viral short-form video content team.

Given raw web search results about a topic, extract a structured research brief.
Return ONLY a raw JSON object — no markdown, no backticks, no preamble.

{
  "facts": ["<specific concrete fact 1>", "<fact 2>", "<fact 3>", "<fact 4>", "<fact 5>"],
  "stats": ["<stat with number/percentage/date 1>", "<stat 2>", "<stat 3>"],
  "angles": ["<surprising or counterintuitive angle 1>", "<surprising angle 2>"],
  "key_insight": "<The single most powerful, shareable insight about this topic>"
}

Rules:
- Facts must be specific and verifiable, not generic
- Stats must include actual numbers, percentages, or dates
- Angles must be genuinely counterintuitive — things most people don't know
- If search results are thin, supplement with your own knowledge
- Never fabricate specific statistics — mark uncertain ones with "approximately\""""

_LLM_ONLY_SYSTEM = """You are a research analyst. Using your training knowledge,
provide a research brief about the given topic. Return ONLY a raw JSON object.

{
  "facts": ["<fact 1>", "<fact 2>", "<fact 3>", "<fact 4>", "<fact 5>"],
  "stats": ["<stat 1>", "<stat 2>", "<stat 3>"],
  "angles": ["<surprising angle 1>", "<surprising angle 2>"],
  "key_insight": "<most powerful, shareable insight>"
}"""

_MINIMAL_FALLBACK = {
    "facts": ["This topic is evolving rapidly with significant real-world impact."],
    "stats": ["Adoption rates growing at double-digit percentages annually."],
    "angles": ["Most people fundamentally misunderstand the core mechanism."],
    "key_insight": "The gap between public perception and reality is larger than most realise.",
}


class ResearchAgent(BaseAgent):
    """
    Gathers real web facts and synthesises a structured ResearchBrief.

    The ResearchBrief becomes the factual backbone consumed by both the
    PlannerAgent (strategic angle decisions) and the NarratorAgent
    (grounding scene claims in real data rather than hallucinations).
    """

    name = "research"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting web research phase...")

        topic_msg = self.get_latest(run_id, "TOPIC_SELECTED")
        topic = (
            topic_msg["payload"]["topic"]
            if topic_msg
            else context.get("topic", "technology")
        )
        self.log(f"Topic: '{topic}'")

        # ── Phase 1: Web search ───────────────────────────────────────────────
        formatted_results, sources, search_ok = self._run_searches(topic)

        # ── Phase 2: LLM synthesis ────────────────────────────────────────────
        brief = self._synthesise(topic, formatted_results, fallback=not search_ok)

        source_label = "web_search" if search_ok else "llm_fallback"
        self.log(
            f"Brief complete [{source_label}] — "
            f"{len(brief['facts'])} facts, {len(brief['stats'])} stats, "
            f"{len(brief['angles'])} angles"
        )
        self.log(f"Key insight: {brief['key_insight'][:100]}")

        payload = {
            "topic": topic,
            "facts": brief["facts"],
            "stats": brief["stats"],
            "angles": brief["angles"],
            "key_insight": brief["key_insight"],
            "sources": sources,
            "source": source_label,
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
                f"Researched '{topic}' via {source_label}. "
                f"{len(brief['facts'])} facts, {len(brief['stats'])} stats. "
                f"Key insight: {brief['key_insight'][:80]}."
            ),
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _run_searches(self, topic: str) -> tuple[str, List[str], bool]:
        """
        Execute two targeted DuckDuckGo queries.
        Returns (formatted_text, source_urls, success_flag).
        """
        queries = [
            f"{topic} statistics facts impact 2024 2025",
            f"{topic} surprising counterintuitive truth",
        ]

        all_results = []
        sources: List[str] = []

        for q in queries:
            self.log(f"  Querying: '{q}'")
            results = search_provider.search(q, max_results=config.RESEARCH_MAX_RESULTS)
            all_results.extend(results)
            sources.extend(r.url for r in results if r.url)

        if not all_results:
            self.log("  No results — switching to LLM-only synthesis")
            return "", [], False

        # Deduplicate by title, cap at 10 results
        seen: set[str] = set()
        unique = []
        for r in all_results:
            if r.title not in seen:
                seen.add(r.title)
                unique.append(r)

        formatted = "\n\n---\n\n".join(r.to_text() for r in unique[:10])
        self.log(f"  {len(unique)} unique results retrieved")
        return formatted, list(dict.fromkeys(sources))[:8], True

    def _synthesise(
        self, topic: str, raw: str, fallback: bool = False
    ) -> Dict[str, Any]:
        """Synthesise a ResearchBrief dict via LLM."""
        if fallback or not raw:
            system = _LLM_ONLY_SYSTEM
            user = f"Topic: {topic}"
        else:
            system = _SYNTHESIS_SYSTEM
            user = f"Topic: {topic}\n\nSearch results:\n\n{raw}"

        try:
            text = generate(system, user)
            return self._parse(text)
        except Exception as e:
            self.log(f"Synthesis LLM call failed: {e} — using minimal fallback")
            return dict(_MINIMAL_FALLBACK)

    def _parse(self, text: str) -> Dict[str, Any]:
        """Parse and normalise the JSON research brief."""
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                data = json.loads(m.group())
            else:
                raise ValueError("Could not parse JSON from research synthesis")

        return {
            "facts": (data.get("facts") or [])[:5],
            "stats": (data.get("stats") or [])[:3],
            "angles": (data.get("angles") or [])[:2],
            "key_insight": data.get("key_insight", ""),
        }
