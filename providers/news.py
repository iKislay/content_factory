# providers/news.py
"""
DuckDuckGo News search provider.

Uses the duckduckgo-search library's .news() endpoint to retrieve
recent, date-stamped news articles about a topic. This adds a recency
layer that encyclopedic sources (Wikipedia) and generic web search
can't provide — critical for evergreen content that references
"what's happening now."

No API key required. Same resilience pattern as providers/search.py:
3 attempts with exponential backoff, empty list on total failure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List


# ─── Data types ───────────────────────────────────────────────────────────────


@dataclass
class NewsArticle:
    """
    A single news article from DuckDuckGo news search.

    Attributes:
        title:   Headline text.
        body:    Article excerpt / lead paragraph.
        source:  Publisher name (e.g. "TechCrunch").
        date:    ISO-format date string (e.g. "2025-05-14T10:32:00+00:00").
        url:     Full article URL.
    """

    title: str
    body: str
    source: str
    date: str
    url: str

    def to_text(self) -> str:
        """Compact string for LLM prompt injection."""
        parts = []
        if self.date:
            parts.append(f"[{self.date[:10]}]")  # just the date part
        if self.source:
            parts.append(f"{self.source}:")
        parts.append(self.title)
        if self.body:
            parts.append(f"— {self.body[:200]}")
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "body": self.body,
            "source": self.source,
            "date": self.date,
            "url": self.url,
        }


# ─── Public API ───────────────────────────────────────────────────────────────


def search_news(topic: str, max_results: int = 5) -> List[NewsArticle]:
    """
    Search DuckDuckGo News for recent articles about *topic*.

    Returns up to max_results articles sorted by recency (most recent first).
    Returns an empty list — not an exception — on total failure.

    Args:
        topic:       Topic string to search for.
        max_results: Maximum number of articles to return (default: 5).

    Returns:
        List of NewsArticle (empty on failure).
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        raise ImportError(
            "duckduckgo-search not installed. Run: pip install duckduckgo-search"
        )

    last_exc: Exception | None = None

    for attempt in range(3):
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.news(topic, max_results=max_results))

            articles = [
                NewsArticle(
                    title=r.get("title", ""),
                    body=r.get("body", ""),
                    source=r.get("source", ""),
                    date=r.get("date", ""),
                    url=r.get("url", ""),
                )
                for r in raw
                if r.get("title") or r.get("body")
            ]

            # Sort most-recent first (ISO date strings sort lexicographically)
            articles.sort(key=lambda a: a.date, reverse=True)
            return articles

        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)

    print(f"[NEWS] All 3 attempts failed for '{topic}': {last_exc}")
    return []
