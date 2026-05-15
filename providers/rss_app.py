# providers/rss_app.py
"""
RSS.app provider for fetching feed items from monitored sources.

RSS.app allows you to follow specific high-quality sources (Twitter accounts,
subreddits, technical blogs, etc.) and trigger content generation when
new updates are posted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import config


@dataclass
class RSSItem:
    """A single item from an RSS feed."""
    id: str
    title: str
    link: str
    published: str
    content: Optional[str] = None
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "link": self.link,
            "published": self.published,
            "content": self.content,
            "source": self.source,
        }


def get_feed_items(feed_id: str, max_items: int = 10) -> List[RSSItem]:
    """
    Fetch latest items from a specific RSS.app feed.

    Args:
        feed_id: The RSS.app feed ID to fetch from.
        max_items: Maximum number of items to return (default: 10).

    Returns:
        List of RSSItem objects (empty on failure).
    """
    api_key = getattr(config, "RSS_APP_API_KEY", None)
    if not api_key:
        print("[RSS_APP] No API key configured")
        return []

    import requests

    url = f"https://api.rss.app/v1/feeds/{feed_id}/items"
    headers = {"X-API-KEY": api_key}

    last_exc: Exception | None = None

    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()

            items = data.get("items", []) if isinstance(data, dict) else []
            return [
                RSSItem(
                    id=item.get("id", ""),
                    title=item.get("title", ""),
                    link=item.get("link", ""),
                    published=item.get("published", ""),
                    content=item.get("content", item.get("description", "")),
                    source=item.get("source", feed_id),
                )
                for item in items[:max_items]
                if item.get("title")
            ]

        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)

    print(f"[RSS_APP] All attempts failed for feed {feed_id}: {last_exc}")
    return []


def get_all_feeds_items(feed_ids: List[str], max_items_per_feed: int = 5) -> List[RSSItem]:
    """
    Fetch items from multiple RSS feeds and combine them.

    Args:
        feed_ids: List of RSS.app feed IDs to fetch from.
        max_items_per_feed: Maximum items per feed (default: 5).

    Returns:
        Combined list of RSSItem objects sorted by publication date (newest first).
    """
    all_items = []

    for feed_id in feed_ids:
        items = get_feed_items(feed_id, max_items=max_items_per_feed)
        all_items.extend(items)

    all_items.sort(key=lambda x: x.published, reverse=True)
    return all_items