import sys
import os
import json

# Add current directory to path
sys.path.append(os.getcwd())

from providers.search import search
from providers.news import search_news
from providers.rss_app import fetch_platform_trends

def test_search():
    print("\n=== Testing Unified Search (DuckDuckGo + Bing Fallback) ===")
    query = "AI trends May 2026"
    try:
        results = search(query, max_results=3)
        if results:
            print(f"✓ Found {len(results)} results for '{query}':")
            for i, r in enumerate(results):
                print(f"  {i+1}. {r.title} ({r.url[:50]}...)")
        else:
            print("✗ No search results found.")
    except Exception as e:
        print(f"✗ Search failed with error: {e}")

def test_news():
    print("\n=== Testing News Search (ddgs) ===")
    topic = "Remote Work"
    try:
        articles = search_news(topic, max_results=3)
        if articles:
            print(f"✓ Found {len(articles)} news articles for '{topic}':")
            for i, a in enumerate(articles):
                print(f"  {i+1}. [{a.date[:10]}] {a.title} ({a.source})")
        else:
            print("✗ No news articles found.")
    except Exception as e:
        print(f"✗ News search failed with error: {e}")

def test_rss_app():
    print("\n=== Testing RSS.app Integration ===")
    platform = "linkedin"
    topic = "Remote Work"
    try:
        result = fetch_platform_trends(platform, topic, max_items=3)
        if result.get("error"):
            print(f"! RSS.app returned expected error/fallback: {result['error']}")
        elif result.get("posts"):
            print(f"✓ Found {len(result['posts'])} trending posts for {platform}/{topic}")
            print(f"✓ Viral DNA: {result.get('viral_dna')}")
        else:
            print("? No posts returned (likely missing API key or no matches)")
    except Exception as e:
        print(f"✗ RSS.app integration failed with error: {e}")

if __name__ == "__main__":
    test_search()
    test_news()
    test_rss_app()
