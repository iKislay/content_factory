# providers/wikipedia.py
"""
Wikipedia REST API provider.

Uses the Wikipedia REST API (no API key required) to fetch structured,
encyclopedic summaries about a topic. This gives the research pipeline a
reliable, citable background layer that web-search snippets cannot match.

The API returns clean, pre-extracted text — no HTML parsing needed.

Endpoint: https://en.wikipedia.org/api/rest_v1/page/summary/{title}

If the direct title lookup fails (404), a search-suggest fallback queries
the Wikipedia OpenSearch API to find the closest matching article title,
then retries the summary endpoint.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional

import requests


# ─── Data types ───────────────────────────────────────────────────────────────


@dataclass
class WikiSummary:
    """
    Structured extract from a Wikipedia article.

    Attributes:
        title:         Canonical Wikipedia article title.
        summary:       Full plain-text extract (typically 3-5 sentences).
        key_sentences: Up to 3 most fact-dense sentences from the summary.
        url:           Canonical Wikipedia page URL.
        found:         False if no Wikipedia article matched the topic.
    """

    title: str
    summary: str
    key_sentences: List[str]
    url: str
    found: bool = True

    def to_text(self) -> str:
        """Compact representation for LLM prompt injection."""
        if not self.found:
            return f"No Wikipedia article found for this topic."
        parts = [f"Wikipedia — {self.title}:", self.summary[:600]]
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "key_sentences": self.key_sentences,
            "url": self.url,
            "found": self.found,
        }


_NOT_FOUND = WikiSummary(
    title="",
    summary="",
    key_sentences=[],
    url="",
    found=False,
)

_REST_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary"
_SEARCH_BASE = "https://en.wikipedia.org/w/api.php"
_HEADERS = {"User-Agent": "ContentFactoryBot/1.0 (research pipeline; non-commercial)"}
_TIMEOUT = 8


# ─── Public API ───────────────────────────────────────────────────────────────


def get_wikipedia_summary(topic: str) -> WikiSummary:
    """
    Fetch a Wikipedia summary for *topic*.

    Tries a direct title lookup first. If that returns 404, falls back to
    the OpenSearch API to find the best-matching article title and retries.

    Args:
        topic: Topic string (e.g. "quantum computing").

    Returns:
        WikiSummary — `found=False` if no article matched.
    """
    # Normalise: capitalise first word, replace spaces with underscores
    normalised = _normalise_title(topic)

    summary = _fetch_summary(normalised)
    if summary.found:
        return summary

    # Fallback: search for the best-matching article title
    best_title = _search_title(topic)
    if best_title:
        summary = _fetch_summary(_normalise_title(best_title))
        if summary.found:
            return summary

    return _NOT_FOUND


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _normalise_title(title: str) -> str:
    """URL-encode a topic string for the Wikipedia REST API path."""
    # Capitalise each word to match Wikipedia title conventions
    normalised = " ".join(w.capitalize() for w in title.split())
    return urllib.parse.quote(normalised, safe="")


def _fetch_summary(encoded_title: str) -> WikiSummary:
    """Call the Wikipedia REST summary endpoint for an encoded title."""
    url = f"{_REST_BASE}/{encoded_title}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code == 404:
            return _NOT_FOUND
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return _NOT_FOUND

    title = data.get("title", "")
    extract = data.get("extract", "")
    page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

    if not extract:
        return _NOT_FOUND

    return WikiSummary(
        title=title,
        summary=extract,
        key_sentences=_extract_key_sentences(extract),
        url=page_url,
        found=True,
    )


def _search_title(query: str) -> Optional[str]:
    """Use Wikipedia OpenSearch to find the closest article title."""
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 3,
        "namespace": 0,
        "format": "json",
    }
    try:
        resp = requests.get(
            _SEARCH_BASE, params=params, headers=_HEADERS, timeout=_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        # OpenSearch returns [query, [titles], [descriptions], [urls]]
        titles = data[1] if len(data) > 1 else []
        return titles[0] if titles else None
    except Exception:
        return None


def _extract_key_sentences(text: str, max_sentences: int = 3) -> List[str]:
    """
    Extract the most fact-dense sentences from a Wikipedia extract.

    Heuristic: sentences containing numbers, percentages, or year references
    are scored higher. Returns up to max_sentences in document order.
    """
    # Split on sentence boundaries (naïve but adequate for Wikipedia extracts)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    def _score(s: str) -> int:
        score = 0
        score += len(re.findall(r"\d+", s)) * 2      # numbers
        score += len(re.findall(r"\d{4}", s)) * 1    # years
        score += len(re.findall(r"\d+%", s)) * 2     # percentages
        return score

    scored = sorted(enumerate(sentences), key=lambda x: _score(x[1]), reverse=True)
    # Take top max_sentences, re-sort by original position for readability
    top_indices = sorted(i for i, _ in scored[:max_sentences])
    return [sentences[i] for i in top_indices if i < len(sentences)]
