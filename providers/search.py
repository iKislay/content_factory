# providers/search.py
"""
DuckDuckGo web search provider.

No API key required. Resilient by design: rate-limit or network errors are
caught and retried with exponential backoff. If all 3 attempts fail, returns
an empty list instead of raising — the pipeline degrades gracefully.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List


@dataclass
class SearchResult:
    """A single web search result."""

    title: str
    snippet: str
    url: str

    def to_text(self) -> str:
        """Compact string representation for LLM prompt injection."""
        parts = []
        if self.title:
            parts.append(f"Title: {self.title}")
        if self.snippet:
            parts.append(f"Snippet: {self.snippet}")
        if self.url:
            parts.append(f"URL: {self.url}")
        return "\n".join(parts)


def search(query: str, max_results: int = 6) -> List[SearchResult]:
    """
    Search DuckDuckGo and return up to max_results results.

    Args:
        query:       Search query string.
        max_results: Maximum number of results to return.

    Returns:
        List of SearchResult (empty list on total failure, not an exception).
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
                raw = list(ddgs.text(query, max_results=max_results))

            return [
                SearchResult(
                    title=r.get("title", ""),
                    snippet=r.get("body", ""),
                    url=r.get("href", ""),
                )
                for r in raw
                if r.get("title") or r.get("body")
            ]

        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)

    print(f"[SEARCH] All 3 attempts failed for '{query}': {last_exc}")
    return []
