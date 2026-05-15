# modules/discovery.py
import random
import requests
from pytrends.request import TrendReq
import config


FALLBACK_TOPICS = [
    "AI in healthcare",
    "Future of remote work",
    "Quantum computing basics",
    "Renewable energy trends",
    "Cybersecurity best practices",
    "Web3 and blockchain",
    "Machine learning for beginners",
    "Electric vehicles future",
    "5G technology impact",
    "Sustainable coding practices",
    "Edge computing explained",
    "Kubernetes for beginners",
    "DevOps trends 2025",
    "ChatGPT alternatives",
    "Data science career path"
]

REGION_MAP = {
    "IN": "india",
    "US": "united_states",
    "GB": "united_kingdom",
    "DE": "germany",
    "FR": "france",
    "JP": "japan",
    "BR": "brazil"
}


def get_trending_topic(region: str = "IN") -> str:
    """Get a trending topic from Google Trends, with fallback."""
    topics = _try_pytrends(region)
    if topics:
        return topics

    for alt_region in ["US", "GB", "DE"]:
        if alt_region != region:
            topics = _try_pytrends(alt_region)
            if topics:
                return topics

    topic = random.choice(FALLBACK_TOPICS)
    print(f"[DISCOVERY] Fallback topic: {topic}")
    return topic


def _try_pytrends(region: str) -> str | None:
    """Try to get trending topic using pytrends."""
    try:
        pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))

        pytrends.build_payload(kw_list=["technology"], timeframe="now 1-H", geo=region)

        interest_over_time = pytrends.interest_over_time()
        if not interest_over_time.empty:
            top_keyword = interest_over_time.sum().idxmax()
            print(f"[DISCOVERY] Trending topic: {top_keyword}")
            return top_keyword

        related_queries = pytrends.related_queries()
        if related_queries and "technology" in related_queries:
            rq = related_queries["technology"]
            if rq is not None and not rq.empty:
                if "top" in rq and not rq["top"].empty:
                    topic = str(rq["top"].iloc[0]["query"])
                    print(f"[DISCOVERY] Trending topic: {topic}")
                    return topic

    except Exception as e:
        print(f"[DISCOVERY] pytrends failed for region {region}: {e}")

    return None