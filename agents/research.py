# agents/research.py
"""
ResearchAgent — multi-source live research with quality gating.

Task 4 extends Task 3's tool-calling mechanism with:
  1. Multi-source coverage: Wikipedia (background) + DuckDuckGo News (recency)
     + web_search (statistics) + fetch_url (depth) = 4 tools, 3 source types.
  2. Research quality scoring: a deterministic scorer classifies the resulting
     brief as RICH / ADEQUATE / THIN and triggers a second research pass on THIN.
  3. Provable influence: the RESEARCH_COMPLETE payload includes quality metrics,
     news_articles, and wikipedia_summary — queryable proof that live web data
     shaped the content.

The LLM drives the research strategy (Task 3) but the quality gate enforces a
minimum standard (Task 4). Together they satisfy "the system pulls live web
information when the task requires it" with verifiable evidence.

Blackboard messages consumed:
  TOPIC_SELECTED  { topic }

Blackboard messages produced:
  TOOL_CALLED       { agent, tool_name, arguments, call_id }  (one per call)
  TOOL_RESULT       { agent, tool_name, call_id, output_summary, duration_ms }
  RESEARCH_COMPLETE {
    topic, facts, stats, angles, key_insight, sources, source,
    tool_calls_count, news_articles, wikipedia_summary, quality
  }
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import config
from agents.base import AgentResult, BaseAgent
from providers.llm import generate_with_tools
from providers.research_quality import score_research
from tools.executor import ToolCall


_RESEARCH_SYSTEM = """You are a research analyst for a viral short-form video content team.

Your task: gather rich, multi-source facts about the given topic using all available tools.

RESEARCH STRATEGY (follow this order):
1. Call search_wikipedia first — get authoritative background and established facts
2. Call search_news — find recent developments (what's happened in the last weeks/months)
3. Call web_search — find specific statistics, surprising facts, and counterintuitive angles
4. Optionally call fetch_url if you find a specific article URL that looks promising

When you have gathered enough material from multiple sources, respond with ONLY this JSON
(no markdown, no backticks, no extra text):
{
  "facts": ["<specific fact 1>", "<fact 2>", "<fact 3>", "<fact 4>", "<fact 5>"],
  "stats": ["<stat with number/percentage/date 1>", "<stat 2>", "<stat 3>"],
  "angles": ["<counterintuitive angle 1>", "<surprising angle 2>"],
  "key_insight": "<single most powerful, shareable insight>",
  "news_headline": "<most interesting recent news headline about this topic, or empty string>"
}

Quality standards:
- Facts must be SPECIFIC (names, dates, places, mechanisms) — never generic
- Stats must contain ACTUAL NUMBERS — percentages, counts, dollar amounts, years
- Angles must be genuinely SURPRISING — things most people don't know
- Try to reference BOTH a Wikipedia fact AND a recent news development in your brief"""

_MINIMAL_FALLBACK: Dict[str, Any] = {
    "facts": ["This topic is evolving rapidly with significant real-world impact."],
    "stats": ["Adoption growing at double-digit rates annually."],
    "angles": ["Most people fundamentally misunderstand the core mechanism."],
    "key_insight": "The gap between public perception and reality is wider than most realise.",
    "news_headline": "",
}


class ResearchAgent(BaseAgent):
    """
    Multi-source research agent with LLM-driven tool use and quality gating.

    The LLM autonomously selects from 4 tools (Wikipedia, News, web search,
    URL fetch) to build a research brief. A deterministic scorer then evaluates
    the brief quality; if it scores THIN, a targeted second pass runs before
    posting RESEARCH_COMPLETE.
    """

    name = "research"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting multi-source live research...")

        topic_msg = self.get_latest(run_id, "TOPIC_SELECTED")
        topic = (
            topic_msg["payload"]["topic"]
            if topic_msg
            else context.get("topic", "technology")
        )
        self.log(f"Topic: '{topic}'")

        from tools import registry

        available_tools = [
            registry.get("search_wikipedia"),
            registry.get("search_news"),
            registry.get("web_search"),
            registry.get("fetch_url"),
        ]
        available_tools = [t for t in available_tools if t is not None]
        executor = self.make_executor(run_id)

        self.log(f"Tools available: {[t.name for t in available_tools]}")

        # ── First research pass ───────────────────────────────────────────────
        brief, all_calls, all_results = self._research_pass(
            topic, available_tools, executor
        )
        wiki_data, news_data = self._extract_live_artifacts(all_results)

        # ── Quality gate ──────────────────────────────────────────────────────
        raw_payload = {**brief, "news_articles": news_data, "wikipedia_summary": wiki_data,
                       "tool_calls_count": len(all_calls), "source": "web_search"}
        quality = score_research(raw_payload)
        self.log(str(quality))

        # Critical failure check: no sources found at all
        has_wikipedia = wiki_data and wiki_data.get("found", False)
        has_news = len(news_data) > 0
        has_web_results = any(
            r.tool_name == "web_search" and r.output and isinstance(r.output, list) and len(r.output) > 0
            for r in all_results
        )
        
        if not has_wikipedia and not has_news and not has_web_results:
            self.log("CRITICAL: No sources found for topic - failing gracefully")
            return AgentResult(
                success=False,
                output={"topic": topic, "reason": "no_sources_found"},
                errors=[f"No research sources found for '{topic}'. Please try a different topic with more available information."],
                reasoning=f"Research failed: no sources found for topic '{topic}'",
                next_agent=None,
            )

        if quality.verdict == "THIN":
            self.log(
                "Quality verdict THIN — running targeted second research pass..."
            )
            brief2, calls2, results2 = self._targeted_second_pass(
                topic, available_tools, executor, brief
            )
            all_calls.extend(calls2)
            all_results.extend(results2)
            # Merge: second pass facts supplement first pass
            brief = self._merge_briefs(brief, brief2)
            wiki_data2, news_data2 = self._extract_live_artifacts(results2)
            wiki_data = wiki_data or wiki_data2
            news_data = news_data + [n for n in news_data2 if n not in news_data]
            raw_payload = {**brief, "news_articles": news_data,
                           "wikipedia_summary": wiki_data,
                           "tool_calls_count": len(all_calls), "source": "web_search"}
            quality = score_research(raw_payload)
            self.log(f"After second pass: {quality}")
            
            # After second pass, if still critically low, fail gracefully
            if quality.score < 3.0:
                self.log(f"CRITICAL: Quality still too low after second pass (score={quality.score})")
                return AgentResult(
                    success=False,
                    output={"topic": topic, "reason": "insufficient_research_quality"},
                    errors=[f"Insufficient research data for '{topic}'. Please try a different topic."],
                    reasoning=f"Research quality too low: score={quality.score} after second pass",
                    next_agent=None,
                )

        # ── Log summary ───────────────────────────────────────────────────────
        self.log(
            f"Research complete — {len(all_calls)} tool calls | "
            f"quality={quality.score:.1f} ({quality.verdict}) | "
            f"sources={quality.sources_used}"
        )
        self.log(f"Key insight: {brief.get('key_insight', '')[:100]}")

        payload = {
            "topic": topic,
            "facts": brief.get("facts", []),
            "stats": brief.get("stats", []),
            "angles": brief.get("angles", []),
            "key_insight": brief.get("key_insight", ""),
            "sources": quality.sources_used,
            "source": "multi_source" if quality.source_diversity > 1 else "web_search",
            "tool_calls_count": len(all_calls),
            "news_articles": [n for n in news_data[:3]],
            "wikipedia_summary": wiki_data or {},
            "quality": quality.to_dict(),
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
                f"Multi-source research for '{topic}': "
                f"{len(all_calls)} tool calls, quality={quality.score:.1f} ({quality.verdict}), "
                f"sources={quality.sources_used}, "
                f"{len(brief.get('facts', []))} facts, "
                f"{len(brief.get('stats', []))} stats."
            ),
        )

    # ── Research passes ───────────────────────────────────────────────────────

    def _research_pass(
        self, topic: str, tools: list, executor: Any
    ) -> tuple[Dict, list, list]:
        """Run one LLM-driven research pass. Returns (brief, calls, results)."""
        try:
            final_text, all_calls, all_results = generate_with_tools(
                system_prompt=_RESEARCH_SYSTEM,
                user_prompt=(
                    f"Research this topic thoroughly using multiple sources: {topic}\n\n"
                    f"Remember: use search_wikipedia first, then search_news, then web_search."
                ),
                tools=tools,
                executor=executor,
                max_rounds=config.MAX_TOOL_ROUNDS,
            )
            return self._parse_brief(final_text), all_calls, all_results
        except Exception as e:
            self.log(f"Research pass failed: {e} — trying direct live-tools fallback")
            brief, calls, results = self._direct_live_tools_fallback(topic, executor)
            if calls or results:
                return brief, calls, results

            self.log("Direct live-tools fallback yielded no data — using LLM-only fallback")
            brief = self._llm_only_research(topic)
            return brief, [], []

    def _targeted_second_pass(
        self, topic: str, tools: list, executor: Any, first_brief: Dict
    ) -> tuple[Dict, list, list]:
        """Targeted second pass focused on filling gaps from the first pass."""
        # Only use Wikipedia and news if first pass was web-only
        targeted_tools = [t for t in tools if t.name in ("search_wikipedia", "search_news")]
        if not targeted_tools:
            targeted_tools = tools

        system = (
            f"You are a research analyst. The initial research on '{topic}' was thin. "
            f"Use search_wikipedia and search_news to find authoritative facts and recent "
            f"news. Return a JSON brief with facts, stats, angles, key_insight, news_headline."
        )
        try:
            text, calls, results = generate_with_tools(
                system_prompt=system,
                user_prompt=f"Find authoritative background and recent news about: {topic}",
                tools=targeted_tools,
                executor=executor,
                max_rounds=2,
            )
            return self._parse_brief(text), calls, results
        except Exception as e:
            self.log(f"Second pass failed: {e}")
            return dict(_MINIMAL_FALLBACK), [], []

    # ── Artifact extraction ───────────────────────────────────────────────────

    def _direct_live_tools_fallback(
        self, topic: str, executor: Any
    ) -> tuple[Dict[str, Any], list, list]:
        """
        Run a deterministic, non-LLM research pass using core tools.

        This keeps research grounded in live sources when the LLM tool loop
        itself fails (provider outage, malformed function-calling response, etc).
        """
        calls: list = []
        results: list = []

        planned_calls = [
            ToolCall(tool_name="search_wikipedia", arguments={"topic": topic}),
            ToolCall(tool_name="search_news", arguments={"topic": topic, "max_results": 5}),
            ToolCall(
                tool_name="web_search",
                arguments={"query": f"{topic} statistics latest", "max_results": 6},
            ),
        ]

        for call in planned_calls:
            calls.append(call)
            results.append(executor.execute(call))

        return self._brief_from_tool_results(topic, results), calls, results

    def _brief_from_tool_results(self, topic: str, results: list) -> Dict[str, Any]:
        """Build a compact research brief directly from tool outputs."""
        facts: List[str] = []
        stats: List[str] = []
        angles: List[str] = []
        headline = ""

        for result in results:
            if not result.is_ok() or result.output is None:
                continue

            output = result.output

            if result.tool_name == "search_wikipedia" and isinstance(output, dict):
                title = str(output.get("title") or topic).strip()
                extract = str(output.get("extract") or "").strip()
                key_facts = output.get("key_facts") or []

                for item in key_facts:
                    if isinstance(item, str):
                        cleaned = item.strip()
                        if cleaned:
                            facts.append(cleaned)

                if extract:
                    facts.append(f"{title}: {extract[:220]}")

            elif result.tool_name == "search_news" and isinstance(output, list):
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title") or "").strip()
                    source = str(item.get("source") or "").strip()
                    if title:
                        if not headline:
                            headline = title
                        facts.append(f"Recent news ({source or 'unknown source'}): {title}")
                        break

            elif result.tool_name == "web_search" and isinstance(output, list):
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title") or "").strip()
                    snippet = str(item.get("snippet") or "").strip()
                    combined = f"{title} {snippet}".strip()
                    if not combined:
                        continue
                    if re.search(r"\b\d[\d,\.]*\b", combined):
                        stats.append(combined[:220])
                    else:
                        angles.append(combined[:220])

        facts = self._dedupe_nonempty(facts, 6)
        stats = self._dedupe_nonempty(stats, 4)
        angles = self._dedupe_nonempty(angles, 3)

        if not facts and not stats and not angles:
            return dict(_MINIMAL_FALLBACK)

        return {
            "facts": facts or list(_MINIMAL_FALLBACK["facts"]),
            "stats": stats or list(_MINIMAL_FALLBACK["stats"]),
            "angles": angles or list(_MINIMAL_FALLBACK["angles"]),
            "key_insight": (
                facts[0]
                if facts
                else stats[0] if stats else _MINIMAL_FALLBACK["key_insight"]
            ),
            "news_headline": headline,
        }

    def _dedupe_nonempty(self, items: List[str], max_items: int) -> List[str]:
        """Return unique non-empty strings in-order, capped to max_items."""
        seen = set()
        merged: List[str] = []
        for item in items:
            cleaned = item.strip()
            if not cleaned:
                continue
            norm = cleaned.lower()
            if norm in seen:
                continue
            seen.add(norm)
            merged.append(cleaned)
            if len(merged) >= max_items:
                break
        return merged

    def _extract_live_artifacts(
        self, results: list
    ) -> tuple[Dict, List[Dict]]:
        """
        Extract Wikipedia summaries and news articles from ToolResult outputs.
        Returns (wiki_dict, news_list).
        """
        wiki_data: Dict = {}
        news_data: List[Dict] = []

        for result in results:
            if not result.is_ok() or result.output is None:
                continue
            output = result.output

            # Wikipedia result: dict with 'found' and 'title' keys
            if (
                result.tool_name == "search_wikipedia"
                and isinstance(output, dict)
                and output.get("found")
            ):
                wiki_data = output

            # News result: list of article dicts with 'date' key
            elif result.tool_name == "search_news" and isinstance(output, list):
                news_data.extend(
                    item for item in output
                    if isinstance(item, dict) and item.get("title")
                )

        return wiki_data, news_data[:3]  # cap at 3 news articles

    # ── Brief merging ─────────────────────────────────────────────────────────

    def _merge_briefs(self, first: Dict, second: Dict) -> Dict:
        """Combine two research briefs, deduplicating facts/stats."""
        def _merge_list(key: str, max_items: int) -> List[str]:
            seen = set()
            merged = []
            for item in (first.get(key) or []) + (second.get(key) or []):
                norm = item.strip().lower()
                if norm not in seen:
                    seen.add(norm)
                    merged.append(item)
            return merged[:max_items]

        return {
            "facts": _merge_list("facts", 6),
            "stats": _merge_list("stats", 4),
            "angles": _merge_list("angles", 3),
            "key_insight": first.get("key_insight") or second.get("key_insight", ""),
            "news_headline": first.get("news_headline") or second.get("news_headline", ""),
        }

    # ── LLM-only fallback ─────────────────────────────────────────────────────

    def _llm_only_research(self, topic: str) -> Dict:
        """Plain LLM call when generate_with_tools() fails entirely."""
        from providers.llm import generate

        system = (
            "You are a research analyst. Return ONLY a raw JSON object with keys: "
            "facts, stats, angles, key_insight, news_headline."
        )
        try:
            text = generate(system, f"Topic: {topic}")
            return self._parse_brief(text)
        except Exception:
            return dict(_MINIMAL_FALLBACK)

    # ── Brief parsing ─────────────────────────────────────────────────────────

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
            "facts": (data.get("facts") or [])[:6],
            "stats": (data.get("stats") or [])[:4],
            "angles": (data.get("angles") or [])[:3],
            "key_insight": data.get("key_insight", _MINIMAL_FALLBACK["key_insight"]),
            "news_headline": data.get("news_headline", ""),
        }
