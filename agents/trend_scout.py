# agents/trend_scout.py
"""
TrendScoutAgent — discovers the trending topic to build content around.

Responsibilities:
  - Query Google Trends via pytrends
  - Apply fallback logic for rate-limited regions
  - Reason about *why* this topic was chosen
  - Post TOPIC_SELECTED to the blackboard with topic + rationale

Blackboard messages produced:
  TOPIC_SELECTED  { topic, rationale, region, source }
"""

from __future__ import annotations

from typing import Any, Dict

from agents.base import AgentResult, BaseAgent
from modules.discovery import get_trending_topic, _try_pytrends, FALLBACK_TOPICS
from state import PipelineState


class TrendScoutAgent(BaseAgent):
    """
    Discovers trending topics and reasons about topic selection.

    This agent wraps the existing discovery module and adds an explicit
    reasoning layer — it records *why* a topic was chosen (trending in
    a region vs. fallback selection), which is posted to the blackboard
    for downstream agents to use as context.
    """

    name = "trend_scout"

    def run(self, run_id: str, context: Dict[str, Any]) -> AgentResult:
        self.log("Starting topic discovery...")

        topic = context.get("topic")  # passed if resuming a crashed run
        source = "resumed"
        region = "N/A"
        rationale = "Resuming from persisted state — topic already selected."

        if not topic:
            topic, source, region = self._discover_topic()
            rationale = self._build_rationale(topic, source, region)

        self.log(f"Topic selected: '{topic}' via {source} ({region})")
        self.log(f"Reasoning: {rationale}")

        self.post_message(
            run_id=run_id,
            msg_type="TOPIC_SELECTED",
            payload={
                "topic": topic,
                "rationale": rationale,
                "source": source,
                "region": region,
            },
            recipient="narrator",
        )

        return AgentResult(
            success=True,
            output={"topic": topic, "rationale": rationale},
            next_agent="narrator",
            reasoning=rationale,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _discover_topic(self) -> tuple[str, str, str]:
        """
        Try Google Trends across regions, return (topic, source, region).
        Falls back to a curated list if Trends is unavailable.
        """
        for region in ["IN", "US", "GB"]:
            self.log(f"Querying Google Trends [{region}]...")
            topic = _try_pytrends(region)
            if topic:
                return topic, "google_trends", region

        # Intelligent fallback — pick based on current hour to add variety
        import time
        idx = int(time.time()) % len(FALLBACK_TOPICS)
        topic = FALLBACK_TOPICS[idx]
        self.log(f"Trends unavailable — using curated fallback: '{topic}'")
        return topic, "curated_fallback", "N/A"

    def _build_rationale(self, topic: str, source: str, region: str) -> str:
        """Construct a human-readable rationale for topic selection."""
        if source == "google_trends":
            return (
                f"'{topic}' is currently trending in the {region} region on "
                f"Google Trends. Selected as the highest-interest topic in the "
                f"past hour — high search velocity indicates strong audience demand."
            )
        return (
            f"Google Trends was rate-limited or unavailable. Selected '{topic}' "
            f"from a curated list of high-value tech topics with consistent "
            f"audience interest."
        )
