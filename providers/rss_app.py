# providers/rss_app.py
"""
RSS.app provider for fetching feed items and creating dynamic feeds.
"""

from __future__ import annotations

import time
import requests
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

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
    """
    
    def __init__(self):
        self.api_key = getattr(config, "RSS_APP_API_KEY", None)
        self.base_url = "https://api.rss.app/v1"
    
    def _get_headers(self) -> dict:
        # RSS.app uses x-api-key header
        return {"x-api-key": self.api_key} if self.api_key else {}
    
    def create_dynamic_feed(self, platform: str, topic: str) -> Optional[str]:
        """
        Create a dynamic RSS feed for platform-specific search.
        """
        if not self.api_key:
            print("[RSS_APP] No API key configured")
            return None
        
        # Determine the best source URL for RSS.app to crawl
        if platform.lower() == "twitter":
            # Using Google News search for Twitter mentions is more stable for RSS.app
            source_url = f"https://news.google.com/search?q={requests.utils.quote(topic)}+site:twitter.com"
        elif platform.lower() == "linkedin":
            source_url = f"https://news.google.com/search?q={requests.utils.quote(topic)}+site:linkedin.com"
        else:
            source_url = f"https://news.google.com/search?q={requests.utils.quote(topic)}"
        
        try:
            # Correct endpoint is /v1/feed (singular) for creation
            url = f"{self.base_url}/feed"
            data = {"url": source_url}
            
            print(f"[RSS_APP] Creating feed for {platform}: {source_url}")
            response = requests.post(url, headers=self._get_headers(), json=data, timeout=15)
            
            if response.status_code in (200, 201):
                feed_data = response.json()
                feed_id = feed_data.get("id")
                print(f"[RSS_APP] Successfully created feed: {feed_id}")
                return feed_id
            else:
                print(f"[RSS_APP] Failed to create feed: {response.status_code} {response.text}")
                return None
        except Exception as e:
            print(f"[RSS_APP] Error creating dynamic feed: {e}")
            return None
    
    def get_feed_items(self, feed_id: str, max_items: int = 10) -> List[RSSItem]:
        """Fetch items from a specific feed."""
        if not self.api_key:
            return []

        url = f"{self.base_url}/feeds/{feed_id}/items"
        
        for attempt in range(3):
            try:
                response = requests.get(url, headers=self._get_headers(), timeout=15)
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
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    print(f"[RSS_APP] Failed to fetch items for {feed_id}: {e}")
        return []

    def analyze_viral_dna(self, posts: List[RSSItem]) -> Dict[str, Any]:
        """Analyze the structural DNA of viral posts using LLM."""
        if not posts:
            return {
                "hook_type": "unknown",
                "formatting": "unknown",
                "sentiment": "neutral",
                "key_patterns": [],
                "cta_style": "None"
            }
        
        from providers.llm import generate
        
        posts_text = "\n\n".join([
            f"Post {i+1}:\nTitle: {p.title}\nContent: {p.content[:300] if p.content else p.title}"
            for i, p in enumerate(posts[:5])
        ])
        
        system = """You are an expert social media analyst. Analyze the provided posts and identify 
their viral DNA. Return ONLY a raw JSON object:
{
  "hook_type": "The Contradiction" | "The Big Stat" | "The Personal Story" | "The Bold Claim" | "The List" | "The Question",
  "formatting": "Bullet-heavy" | "Short sentences" | "Thread format" | "Long-form",
  "sentiment": "Urgent" | "Professional" | "Casual" | "Controversial" | "Inspirational",
  "key_patterns": ["string", "string"],
  "cta_style": "Question" | "Call to action" | "None"
}"""
        
        try:
            raw = generate(system, f"Analyze these viral posts:\n\n{posts_text}")
            # Clean up JSON from markdown if necessary
            raw = re.sub(r"```json\s*", "", raw)
            raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE).strip()
            return json.loads(raw)
        except Exception as e:
            print(f"[RSS_APP] Viral DNA analysis failed: {e}")
            return {"hook_type": "unknown", "formatting": "unknown", "sentiment": "neutral", "key_patterns": [], "cta_style": "None"}

_rss_provider = RSSAppProvider()

def get_feed_items(feed_id: str, max_items: int = 10) -> List[RSSItem]:
    return _rss_provider.get_feed_items(feed_id, max_items)

def get_all_feeds_items(feed_ids: List[str], max_items_per_feed: int = 5) -> List[RSSItem]:
    all_items = []
    for fid in feed_ids:
        if fid:
            all_items.extend(get_feed_items(fid, max_items_per_feed))
    all_items.sort(key=lambda x: x.published, reverse=True)
    return all_items

def fetch_platform_trends(platform: str, topic: str, max_items: int = 10) -> Dict[str, Any]:
    """Main entry point for trend analysis via RSS.app."""
    feed_id = _rss_provider.create_dynamic_feed(platform, topic)
    if not feed_id:
        return {
            "posts": [],
            "feed_id": None,
            "viral_dna": {"hook_type": "unknown", "formatting": "unknown", "sentiment": "neutral"},
            "error": "Failed to create or access feed"
        }
    
    posts = _rss_provider.get_feed_items(feed_id, max_items)
    viral_dna = _rss_provider.analyze_viral_dna(posts)
    
    return {
        "posts": [p.to_dict() for p in posts],
        "feed_id": feed_id,
        "viral_dna": viral_dna
    }
