# providers/rss_app.py
"""
RSS.app provider for fetching feed items from monitored sources.

RSS.app allows you to follow specific high-quality sources (Twitter accounts,
subreddits, technical blogs, etc.) and trigger content generation when
new updates are posted.

Also supports dynamic RSS feed creation for platform-specific search queries
(Twitter, LinkedIn) using RSS.app's feed creation API.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import config
import requests


@dataclass
class RSSItem:
    """A single item from an RSS feed."""
    id: str
    title: str
    link: str
    published: str
    content: Optional[str] = None
    source: Optional[str] = None
    engagement: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "link": self.link,
            "published": self.published,
            "content": self.content,
            "source": self.source,
            "engagement": self.engagement,
        }


class RSSAppProvider:
    """
    RSS.app provider with dynamic feed creation support.
    
    Supports:
    - Fetching items from existing feeds
    - Creating dynamic feeds for platform-specific searches
    - Pattern extraction for viral content analysis
    """
    
    def __init__(self):
        self.api_key = getattr(config, "RSS_APP_API_KEY", None)
        self.base_url = "https://api.rss.app/v1"
    
    def _get_headers(self) -> dict:
        return {"X-API-KEY": self.api_key} if self.api_key else {}
    
    def create_dynamic_feed(self, platform: str, topic: str, query: str = None) -> Optional[str]:
        """
        Create a dynamic RSS feed for platform-specific search.
        
        Args:
            platform: "twitter" or "linkedin"
            topic: The topic to search for
            query: Optional custom query (if not provided, constructs one)
        
        Returns:
            Feed ID if successful, None otherwise
        """
        if not self.api_key:
            print("[RSS_APP] No API key configured - cannot create dynamic feed")
            return None
        
        if query is None:
            if platform.lower() == "twitter":
                query = f"site:twitter.com {topic}"
            elif platform.lower() == "linkedin":
                query = f"site:linkedin.com/posts {topic}"
            else:
                query = topic
        
        try:
            url = f"{self.base_url}/feeds"
            data = {
                "url": f"https://www.google.com/search?q={requests.utils.quote(query)}",
                "title": f"{platform.capitalize()} - {topic}",
            }
            response = requests.post(url, headers=self._get_headers(), json=data, timeout=15)
            
            if response.status_code == 201:
                feed_data = response.json()
                feed_id = feed_data.get("id")
                print(f"[RSS_APP] Created dynamic feed for {platform}/{topic}: {feed_id}")
                return feed_id
            else:
                print(f"[RSS_APP] Failed to create feed: {response.status_code} {response.text}")
                return None
        except Exception as e:
            print(f"[RSS_APP] Error creating dynamic feed: {e}")
            return None
    
    def fetch_viral_examples(
        self, 
        feed_id: str, 
        max_items: int = 10,
    ) -> List[RSSItem]:
        """
        Fetch items from a feed.

        Args:
            feed_id: RSS.app feed ID
            max_items: Maximum items to return

        Returns:
            List of RSSItem.
        """
        return get_feed_items(feed_id, max_items=max_items)    
    def analyze_viral_dna(self, posts: List[RSSItem]) -> Dict[str, Any]:
        """
        Analyze the structural DNA of viral posts.
        
        Args:
            posts: List of RSS posts to analyze
        
        Returns:
            Dict with hook_type, formatting, sentiment, and examples
        """
        if not posts:
            return {
                "hook_type": "unknown",
                "formatting": "unknown",
                "sentiment": "neutral",
                "examples": [],
            }
        
        from providers.llm import generate
        
        posts_text = "\n\n".join([
            f"Post {i+1}:\nTitle: {p.title}\nContent: {p.content or p.title}"
            for i, p in enumerate(posts[:5])
        ])
        
        system = """You are an expert social media analyst. Analyze viral posts and identify 
their structural DNA. Return ONLY a raw JSON object:

{
  "hook_type": "The Contradiction" | "The Big Stat" | "The Personal Story" | "The Bold Claim" | "The List" | "The Question" | "Unknown",
  "formatting": "Bullet-heavy" | "Short sentences" | "Thread format" | "Long-form" | "Mixed",
  "sentiment": "Urgent" | "Professional" | "Casual" | "Controversial" | "Inspirational" | "Neutral",
  "key_patterns": ["pattern 1", "pattern 2", "pattern 3"],
  "cta_style": "Question" | "Call to action" | "None" | "Hashtag"
}"""
        
        user = f"Analyze these viral posts:\n\n{posts_text}"
        
        try:
            raw = generate(system, user)
            import re, json
            raw = re.sub(r"```json\s*", "", raw)
            raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE).strip()
            return json.loads(raw)
        except Exception as e:
            print(f"[RSS_APP] Failed to analyze viral DNA: {e}")
            return {
                "hook_type": "unknown",
                "formatting": "unknown",
                "sentiment": "neutral",
                "key_patterns": [],
                "cta_style": "None",
            }


_rss_provider = RSSAppProvider()


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


def fetch_platform_trends(platform: str, topic: str, max_items: int = 10) -> Dict[str, Any]:
    """
    Fetch trending posts from a specific platform for a topic.
    
    This is the main entry point for the RSS.app bridge functionality.
    
    Args:
        platform: "twitter" or "linkedin"
        topic: The topic to search for
        max_items: Maximum number of posts to fetch
    
    Returns:
        Dict with:
            - posts: List of RSSItem
            - feed_id: The created feed ID
            - viral_dna: Analysis of what makes these posts viral
    """
    provider = _rss_provider
    
    if not provider.api_key:
        print("[RSS_APP] No API key - using fallback search")
        return {
            "posts": [],
            "feed_id": None,
            "viral_dna": {"hook_type": "unknown", "formatting": "unknown", "sentiment": "neutral"},
            "error": "No RSS_APP_API_KEY configured",
        }
    
    feed_id = provider.create_dynamic_feed(platform, topic)
    if not feed_id:
        return {
            "posts": [],
            "feed_id": None,
            "viral_dna": {"hook_type": "unknown", "formatting": "unknown", "sentiment": "neutral"},
            "error": "Failed to create dynamic feed",
        }
    
    posts = provider.fetch_viral_examples(feed_id, max_items=max_items)
    viral_dna = provider.analyze_viral_dna(posts)
    
    return {
        "posts": [p.to_dict() for p in posts],
        "feed_id": feed_id,
        "viral_dna": viral_dna,
    }