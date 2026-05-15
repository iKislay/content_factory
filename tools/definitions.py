# tools/definitions.py
"""
Concrete tool implementations registered on the global registry.

Import this module to trigger all @registry.tool() decorations.
All eight tools are usable via generate_with_tools() or directly.

Tools registered here:
  1. web_search         — DuckDuckGo query → list of {title, snippet, url}
  2. fetch_url          — HTTP GET → plain-text page content (HTML stripped)
  3. get_trending_topic — Google Trends (with fallback) → topic string
  4. generate_image     — Pollinations.ai → local file path
  5. synthesize_tts     — Kokoro TTS → {path, duration} dict
  6. search_wikipedia   — Wikipedia REST API → structured summary + key facts
  7. search_news        — DuckDuckGo News → recent articles with dates
  8. fetch_rss_feed     — RSS.app feeds → list of feed items
"""

from __future__ import annotations

import html
import re
import time
from typing import Any, Dict, List

from tools.registry import registry  # global singleton


# ─── 1. web_search ────────────────────────────────────────────────────────────


@registry.tool(
    name="web_search",
    description=(
        "Search the web using DuckDuckGo and return a list of results. "
        "Each result contains 'title', 'snippet', and 'url' fields. "
        "Use this to find recent news, statistics, and facts about a topic."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to run on DuckDuckGo.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 6).",
                "default": 6,
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str, max_results: int = 6) -> List[Dict[str, str]]:
    """Search DuckDuckGo and return structured results."""
    from providers.search import search as ddg_search

    results = ddg_search(query, max_results=max_results)
    return [
        {"title": r.title, "snippet": r.snippet, "url": r.url}
        for r in results
    ]


# ─── 2. fetch_url ─────────────────────────────────────────────────────────────


@registry.tool(
    name="fetch_url",
    description=(
        "Fetch the text content of a URL. Returns plain text with HTML tags "
        "stripped. Use after web_search to read the full content of an interesting "
        "article or page."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from.",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters to return (default: 2000).",
                "default": 2000,
            },
        },
        "required": ["url"],
    },
)
def fetch_url(url: str, max_chars: int = 2000) -> str:
    """Fetch a URL and return stripped plain text."""
    import requests

    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ContentBot/1.0)"},
        )
        resp.raise_for_status()
        text = resp.text
    except Exception as exc:
        return f"Failed to fetch {url}: {exc}"

    # Strip HTML tags, decode entities, collapse whitespace
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text[:max_chars]


# ─── 3. get_trending_topic ────────────────────────────────────────────────────


@registry.tool(
    name="get_trending_topic",
    description=(
        "Query Google Trends to find a currently trending topic in a region. "
        "Returns a single topic string. Falls back to a curated list if "
        "Trends is rate-limited."
    ),
    parameters={
        "type": "object",
        "properties": {
            "region": {
                "type": "string",
                "description": (
                    "Two-letter region code to query trends for. "
                    "Supported: IN, US, GB, DE, FR, JP, BR (default: IN)."
                ),
                "default": "IN",
            },
        },
        "required": [],
    },
)
def get_trending_topic(region: str = "IN") -> str:
    """Delegate to the existing discovery module."""
    from modules.discovery import get_trending_topic as _get

    return _get(region=region)


# ─── 4. generate_image ────────────────────────────────────────────────────────


def generate_image_fallback(prompt: str, scene_id: int, output_dir: str) -> str:
    """Fallback: Generate a placeholder image with text when primary fails."""
    import os
    from PIL import Image, ImageDraw, ImageFont

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"image_scene_{scene_id}.png")

    width, height = 1024, 1792
    img = Image.new("RGB", (width, height), color="#1a1a2e")
    draw = ImageDraw.Draw(img)

    text = f"Scene {scene_id}\n\n{prompt[:100]}..."
    bbox = draw.textbbox((0, 0), text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    position = ((width - text_width) // 2, (height - text_height) // 2)

    draw.text(position, text, fill="#ffffff", align="center")

    img.save(output_path)
    return output_path


@registry.tool(
    name="generate_image",
    description=(
        "Generate an image from a text prompt using Pollinations.ai and save it "
        "to disk. Returns the local file path of the saved image."
    ),
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed image generation prompt.",
            },
            "scene_id": {
                "type": "integer",
                "description": "Scene identifier (used for the output filename).",
            },
            "output_dir": {
                "type": "string",
                "description": "Directory to save the generated image.",
            },
        },
        "required": ["prompt", "scene_id", "output_dir"],
    },
    fallback=generate_image_fallback,
)
def generate_image(prompt: str, scene_id: int, output_dir: str) -> str:
    """Delegate to the existing images provider."""
    from providers.images import generate_image as _gen

    return _gen(prompt=prompt, scene_id=scene_id, output_dir=output_dir)


# ─── 5. synthesize_tts ────────────────────────────────────────────────────────


def synthesize_tts_fallback(text: str, scene_id: int, output_dir: str) -> Dict[str, Any]:
    """Fallback: Create a silent audio file when TTS fails."""
    import os
    import numpy as np

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"audio_scene_{scene_id}.wav")

    sample_rate = 24000
    duration_sec = 3.0
    samples = int(sample_rate * duration_sec)
    silence = np.zeros(samples, dtype=np.float32)

    try:
        import soundfile as sf
        sf.write(output_path, silence, sample_rate)
    except Exception:
        return {"path": None, "duration": 0, "error": "Fallback: silent audio created (no TTS)"}

    return {"path": output_path, "duration": duration_sec, "degraded": True}


@registry.tool(
    name="synthesize_tts",
    description=(
        "Synthesise speech from text using Kokoro TTS and save it as a WAV file. "
        "Returns a dict with 'path' (file path) and 'duration' (seconds)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The narration text to synthesise.",
            },
            "scene_id": {
                "type": "integer",
                "description": "Scene identifier (used for the output filename).",
            },
            "output_dir": {
                "type": "string",
                "description": "Directory to save the generated audio file.",
            },
        },
        "required": ["text", "scene_id", "output_dir"],
    },
    fallback=synthesize_tts_fallback,
)
def synthesize_tts(text: str, scene_id: int, output_dir: str) -> Dict[str, Any]:
    """Synthesise speech via Kokoro TTS and return path + duration."""
    import os

    import config

    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf
    except ImportError:
        raise RuntimeError(
            "Kokoro TTS not installed. Run: pip install kokoro-onnx soundfile"
        )

    kokoro = Kokoro.from_pretrained()
    voice_style = kokoro.get_voice_style(config.KOKORO_VOICE)
    audio, _ = kokoro.create(text=text, voice=voice_style, speed=1.0, lang="en-us")

    output_path = os.path.join(output_dir, f"audio_scene_{scene_id}.wav")
    sf.write(output_path, audio, config.KOKORO_SAMPLE_RATE)

    duration = round(len(audio) / config.KOKORO_SAMPLE_RATE, 3)
    return {"path": output_path, "duration": duration}


# ─── 6. search_wikipedia ──────────────────────────────────────────────────────


@registry.tool(
    name="search_wikipedia",
    description=(
        "Fetch a structured Wikipedia summary for a topic. Returns the article "
        "title, a plain-text extract (encyclopedic background), key fact-dense "
        "sentences, and the article URL. Use this FIRST to establish authoritative "
        "background before searching for statistics or news."
    ),
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Topic to look up on Wikipedia (e.g. 'quantum computing').",
            },
        },
        "required": ["topic"],
    },
)
def search_wikipedia(topic: str) -> Dict[str, Any]:
    """Fetch a Wikipedia summary and return it as a serialisable dict."""
    from providers.wikipedia import get_wikipedia_summary

    result = get_wikipedia_summary(topic)
    return result.to_dict()


# ─── 7. search_news ───────────────────────────────────────────────────────────


@registry.tool(
    name="search_news",
    description=(
        "Search for recent news articles about a topic using DuckDuckGo News. "
        "Returns articles with title, body excerpt, source name, publication date, "
        "and URL. Use this to find what's happening RIGHT NOW — complements "
        "Wikipedia's encyclopedic background with current events."
    ),
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Topic to search news for.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of articles to return (default: 5).",
                "default": 5,
            },
        },
        "required": ["topic"],
    },
)
def search_news(topic: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search DuckDuckGo News and return serialisable article dicts."""
    from providers.news import search_news as _search

    articles = _search(topic, max_results=max_results)
    return [a.to_dict() for a in articles]


# ─── 8. fetch_rss_feed ─────────────────────────────────────────────────────────


@registry.tool(
    name="fetch_rss_feed",
    description=(
        "Fetch the latest items from RSS.app feeds. Use this to monitor "
        "specific high-quality sources (Twitter accounts, subreddits, tech blogs) "
        "for new content. Returns items with title, link, published date, and content."
    ),
    parameters={
        "type": "object",
        "properties": {
            "feed_ids": {
                "type": "string",
                "description": "Comma-separated list of RSS.app feed IDs to fetch from.",
            },
            "max_items_per_feed": {
                "type": "integer",
                "description": "Maximum items to fetch per feed (default: 5).",
                "default": 5,
            },
        },
        "required": ["feed_ids"],
    },
)
def fetch_rss_feed(feed_ids: str, max_items_per_feed: int = 5) -> List[Dict[str, Any]]:
    """Fetch latest items from RSS.app feeds."""
    from providers.rss_app import get_all_feeds_items

    feed_id_list = [fid.strip() for fid in feed_ids.split(",") if fid.strip()]
    if not feed_id_list:
        return []

    items = get_all_feeds_items(feed_id_list, max_items_per_feed=max_items_per_feed)
    return [item.to_dict() for item in items]


# ─── 9. fetch_platform_trends ──────────────────────────────────────────────────

@registry.tool(
    name="fetch_platform_trends",
    description=(
        "Fetch trending posts from a specific platform (Twitter/X or LinkedIn) "
        "for a given topic. Uses RSS.app to create a dynamic feed and analyze "
        "viral patterns. Returns top-performing posts and their structural DNA "
        "(hook type, formatting style, sentiment)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": "Platform to search: 'twitter' or 'linkedin'.",
                "enum": ["twitter", "linkedin"],
            },
            "topic": {
                "type": "string",
                "description": "Topic to search for (e.g., 'AI trends 2026').",
            },
            "max_items": {
                "type": "integer",
                "description": "Maximum number of posts to fetch (default: 10).",
                "default": 10,
            },
        },
        "required": ["platform", "topic"],
    },
)
def fetch_platform_trends(platform: str, topic: str, max_items: int = 10) -> Dict[str, Any]:
    """Fetch trending posts from a platform and analyze viral patterns."""
    from providers.rss_app import fetch_platform_trends as _fetch_trends

    return _fetch_trends(platform=platform, topic=topic, max_items=max_items)

