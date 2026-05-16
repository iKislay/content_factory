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

IMPORTANT PRIORITY ORDER for topic discovery:
1. FIRST: Call fetch_platform_trends with platform='twitter' and topic='general' to get latest trending posts from Twitter/X
2. If Twitter returns nothing, try fetch_platform_trends with platform='linkedin' and topic='technology'
3. If platform trends unavailable, call get_trending_topic from Google Trends
4. Use web_search to verify topics have recent news and are video-worthy
5. Based on what you find, decide on the 3 best topics

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
        
        # Empty string means user rejected and wants fresh discovery
        if user_provided_topic == "":
            user_provided_topic = None
        
        auto_keywords = ['auto-discover', 'find topic', 'discover', 'trending', 'generate topic']
        is_auto_topic = user_provided_topic and any(kw in user_provided_topic.lower() for kw in auto_keywords)
        
        # Determine base_topic BEFORE any usage (was previously used before being defined — NameError bug)
        base_topic = None
        if user_provided_topic and user_provided_topic.strip() and not is_auto_topic:
            base_topic = user_provided_topic.strip()
            self.log(f"User provided base topic: '{base_topic}' — finding related angles...")
        
        # Check RSS feeds availability
        rss_feed_ids = getattr(config, "RSS_APP_FEED_IDS", [])
        has_rss_feeds = rss_feed_ids and any(fid.strip() for fid in rss_feed_ids if fid.strip())
        
        # Priority: RSS feeds first (if available and not user-forced specific topic)
        if has_rss_feeds and not base_topic:
            self.log(f"Using RSS feeds as primary source (feeds: {rss_feed_ids})")
            from providers.rss_app import get_all_feeds_items
            try:
                rss_items = get_all_feeds_items([fid.strip() for fid in rss_feed_ids if fid.strip()], max_items_per_feed=5)
                if rss_items:
                    self.log(f"RSS feeds returned {len(rss_items)} items — using as primary source")
                    rss_topics = [
                        {"topic": item.title, "rationale": f"From RSS feed: {item.source or 'monitored source'}"}
                        for item in rss_items[:3]
                    ]
                    topic = rss_topics[0]["topic"]
                    rationale = rss_topics[0]["rationale"]
                    self._post_selected(run_id, topic, rationale, "rss_feed", "IN", topics=rss_topics)
                    return AgentResult(
                        success=True,
                        output={"topic": topic, "rationale": rationale, "topics": rss_topics},
                        next_agent="research",
                        reasoning=f"Found {len(rss_topics)} topics via RSS feeds",
                    )
            except Exception as rss_err:
                self.log(f"RSS feed fetch failed: {rss_err} — falling back to search")

        # Resume path — only if not a fresh run with base_topic
        # Check if this is actually a resumed run by looking at existing messages
        previous_msg = self.get_latest(run_id, "TOPIC_SELECTED")
        is_resumed = previous_msg is not None and context.get("topic") and context["topic"] != "" and not base_topic
        
        if is_resumed:
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
            registry.get("fetch_rss_feed"),
            registry.get("fetch_platform_trends"),
            registry.get("get_trending_topic"),
            registry.get("web_search"),
        ]

        # RSS check already done at start - removed duplicate

        executor = self.make_executor(run_id)

        # Initialize here so the except path and source= line never hit UnboundLocalError
        all_calls: list = []
        all_results: list = []

        try:
            if base_topic:
                user_prompt = f"""[CRITICAL INSTRUCTION: DO NOT CALL get_trending_topic. Skip step 1 of your system instructions entirely.]

Based on the user's specific requested topic '{base_topic}', find the TOP 3 MOST VIRAL ANGLES or sub-topics that would make a compelling short video right now. 

For each angle, provide:
- A specific, catchy video title/angle
- Why it's currently trending or viral-worthy

Search for recent news, trends, or developments related to '{base_topic}' to find the most timely and engaging angles."""
            else:
                rss_feed_ids = getattr(config, "RSS_APP_FEED_IDS", [])
                rss_instruction = ""
                if rss_feed_ids and any(rss_feed_ids):
                    feed_ids_str = ",".join(rss_feed_ids)
                    rss_instruction = f"\n\nYou have access to RSS feeds. Use fetch_rss_feed with feed_ids='{feed_ids_str}' to get the latest items from your monitored sources first."
                user_prompt = f"Find the top 3 best topics for a viral short video right now. Search for what's currently trending.{rss_instruction}"
            
            final_text, all_calls, all_results = generate_with_tools(
                system_prompt=_SCOUT_SYSTEM,
                user_prompt=user_prompt,
                tools=available_tools,
                executor=executor,
                max_rounds=config.MAX_TOOL_ROUNDS,
            )
            
            # Validate: check if web_search returned any results for user-provided topics
            if base_topic:
                search_empty = self._check_search_results_empty(all_results)
                if search_empty:
                    # Try a broader search approach
                    broader_query = f"{base_topic} latest news 2026"
                    from providers.search import search as do_search
                    broader_results = do_search(broader_query, max_results=3)
                    if broader_results:
                        self.log(f"Broader search '{broader_query}' returned {len(broader_results)} results")
                    else:
                        # All search methods exhausted - fail with clear message
                        self.log(f"Search failed for '{base_topic}' — showing error to user")
                        return AgentResult(
                            success=False,
                            output={"topic": base_topic, "reason": "no_search_results"},
                            errors=[f"Could not find any results for '{base_topic}'. Please try a different topic."],
                            reasoning=f"Search failed for user topic",
                            next_agent=None,
                        )
            
            topics_data = self._parse_response(final_text)
            
            # Ensure we got valid topics from the LLM
            if not topics_data:
                self.log("No valid topics parsed from LLM response — using fallback")
                if base_topic:
                    topic = base_topic
                    rationale = f"Proceeding with requested topic: {base_topic}"
                else:
                    topic, rationale = self._fallback_topic()
                topics_data = [{"topic": topic, "rationale": rationale}]
            else:
                topic = topics_data[0]["topic"]
                rationale = topics_data[0]["rationale"]
        except Exception as e:
            self.log(f"Tool-use failed: {e} — using fallback discovery")
            if base_topic:
                topic = base_topic
                rationale = "User provided topic (tool use failed for subtopics)."
            else:
                topic, rationale = self._fallback_topic()
            topics_data = [{"topic": topic, "rationale": rationale}]

        # Final safety check: if LLM returned nothing useful, fall back to user's keyword
        if not topic:
            if base_topic:
                topic = base_topic
                rationale = f"Using your requested topic: {base_topic}"
            else:
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

    def _check_search_results_empty(self, all_results: list) -> bool:
        """Check if any web_search calls returned empty results."""
        for result in all_results:
            if result.tool_name == "web_search":
                output = result.output
                if output is None or (isinstance(output, list) and len(output) == 0):
                    return True
        return False

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

