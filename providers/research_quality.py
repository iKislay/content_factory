# providers/research_quality.py
"""
Research quality scorer — quantifies how much live data a research brief contains.

Zero LLM calls. Pure deterministic scoring based on the structure and diversity
of the RESEARCH_COMPLETE payload. The resulting ResearchQuality dict is embedded
directly in the blackboard message as provable, queryable evidence of live research.

Scoring rubric (max 10.0):
  fact_count >= 5         → +3.0
  fact_count 3–4          → +1.5
  stat_count >= 3         → +2.0
  stat_count 1–2          → +1.0
  source_diversity == 3   → +2.0  (web + news + wikipedia)
  source_diversity == 2   → +1.0
  has_recent_news         → +2.0  (at least one news article found)
  has_wikipedia           → +1.0  (Wikipedia article was found)

Verdicts:
  >= 7.0  → RICH      (proceed normally)
  4.0–6.9 → ADEQUATE  (proceed, log warning)
  < 4.0   → THIN      (trigger second research pass)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


# ─── Data types ───────────────────────────────────────────────────────────────


@dataclass
class ResearchQuality:
    """
    Quantified quality assessment of a RESEARCH_COMPLETE payload.

    Attributes:
        score:          Composite quality score (0.0–10.0).
        fact_count:     Number of unique facts in the brief.
        stat_count:     Facts that contain numbers/percentages (more informative).
        source_diversity: How many distinct source types contributed (1–3).
        has_recent_news:  True if news articles are present in the payload.
        has_wikipedia:    True if a Wikipedia summary is present.
        sources_used:     List of source type labels, e.g. ["web", "news", "wikipedia"].
        verdict:          "RICH" | "ADEQUATE" | "THIN"
    """

    score: float
    fact_count: int
    stat_count: int
    source_diversity: int
    has_recent_news: bool
    has_wikipedia: bool
    sources_used: List[str]
    verdict: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "fact_count": self.fact_count,
            "stat_count": self.stat_count,
            "source_diversity": self.source_diversity,
            "has_recent_news": self.has_recent_news,
            "has_wikipedia": self.has_wikipedia,
            "sources_used": self.sources_used,
            "verdict": self.verdict,
        }

    def __str__(self) -> str:
        return (
            f"ResearchQuality(score={self.score:.1f} verdict={self.verdict} "
            f"facts={self.fact_count} stats={self.stat_count} "
            f"sources={self.sources_used})"
        )


# ─── Public API ───────────────────────────────────────────────────────────────


def score_research(payload: Dict[str, Any]) -> ResearchQuality:
    """
    Score a RESEARCH_COMPLETE payload and return a ResearchQuality result.

    Args:
        payload: The full payload dict from a RESEARCH_COMPLETE blackboard message.

    Returns:
        ResearchQuality with score, counts, diversity, and verdict.
    """
    facts: List[str] = payload.get("facts") or []
    stats: List[str] = payload.get("stats") or []
    source: str = payload.get("source", "")
    news_articles: List = payload.get("news_articles") or []
    wikipedia: Dict = payload.get("wikipedia_summary") or {}
    tool_calls_count: int = payload.get("tool_calls_count", 0)

    # ── Count facts and stats ─────────────────────────────────────────────────
    fact_count = len([f for f in facts if f.strip()])
    stat_count = len([s for s in stats if s.strip()])

    # Additional: count facts that contain numeric data (as supplementary stats)
    numeric_in_facts = sum(1 for f in facts if re.search(r"\d", f))

    # ── Determine sources used ────────────────────────────────────────────────
    sources_used: List[str] = []

    # Web search was used if source == "web_search" or tool calls include search
    if source == "web_search" or tool_calls_count > 0:
        sources_used.append("web")

    # News articles present
    has_recent_news = len(news_articles) > 0
    if has_recent_news:
        sources_used.append("news")

    # Wikipedia summary present and found
    has_wikipedia = bool(wikipedia.get("found", False))
    if has_wikipedia:
        sources_used.append("wikipedia")

    # If no sources detected but we have facts, assume web fallback
    if not sources_used and fact_count > 0:
        sources_used = ["web"]

    source_diversity = len(sources_used)

    # ── Score calculation ─────────────────────────────────────────────────────
    score = 0.0

    # Fact count contribution
    if fact_count >= 5:
        score += 3.0
    elif fact_count >= 3:
        score += 1.5
    elif fact_count >= 1:
        score += 0.5

    # Stat count contribution
    if stat_count >= 3:
        score += 2.0
    elif stat_count >= 1:
        score += 1.0

    # Bonus for numeric density in facts
    if numeric_in_facts >= 3:
        score += 0.5

    # Source diversity contribution
    if source_diversity >= 3:
        score += 2.0
    elif source_diversity == 2:
        score += 1.0

    # Recency bonus
    if has_recent_news:
        score += 2.0

    # Wikipedia bonus
    if has_wikipedia:
        score += 1.0

    score = min(10.0, round(score, 2))

    # ── Verdict ───────────────────────────────────────────────────────────────
    if score >= 7.0:
        verdict = "RICH"
    elif score >= 4.0:
        verdict = "ADEQUATE"
    else:
        verdict = "THIN"

    return ResearchQuality(
        score=score,
        fact_count=fact_count,
        stat_count=stat_count,
        source_diversity=source_diversity,
        has_recent_news=has_recent_news,
        has_wikipedia=has_wikipedia,
        sources_used=sources_used,
        verdict=verdict,
    )
