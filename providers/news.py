# providers/news.py
"""
DuckDuckGo News search provider using the ddgs library.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

@dataclass
class NewsArticle:
    """A single news article from DuckDuckGo news search."""
    title: str
    body: str
    source: str
    date: str
    url: str

    def to_text(self) -> str:
        """Compact string for LLM prompt injection."""
        parts = []
        if self.date:
            parts.append(f"[{self.date[:10]}]")
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

def search_news(topic: str, max_results: int = 5) -> List[NewsArticle]:
    """
    Search DuckDuckGo News for recent articles about *topic*.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        print("[NEWS] ddgs not installed")
        return []

    for attempt in range(3):
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.news(topic, max_results=max_results))

            if not raw:
                continue

            articles = [
                NewsArticle(
                    title=r.get("title", ""),
                    body=r.get("body", ""),
                    source=r.get("source", ""),
                    date=r.get("date", ""),
                    url=r.get("url", ""),
                )
                for r in raw
            ]

            # Sort most-recent first
            articles.sort(key=lambda a: a.date, reverse=True)
            print(f"[NEWS] DuckDuckGo News returned {len(articles)} articles for '{topic}'")
            return articles

        except Exception as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"[NEWS] All 3 attempts failed for '{topic}': {exc}")

    return []
