# providers/search.py
"""
Robust web search provider using DuckDuckGo (via ddgs or duckduckgo_search) with Bing fallback.
"""

from __future__ import annotations

import time
import requests
from dataclasses import dataclass
from typing import List
from bs4 import BeautifulSoup

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

def _get_ddgs_client():
    """Try to import DDGS from ddgs or duckduckgo_search."""
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            return DDGS
        except ImportError:
            return None

def search(query: str, max_results: int = 6) -> List[SearchResult]:
    """
    Search using DuckDuckGo and fallback to Bing scraping.
    """
    print(f"[SEARCH] Searching for: '{query}'")
    
    # 1. Try DuckDuckGo
    DDGS_Class = _get_ddgs_client()
    if DDGS_Class:
        try:
            with DDGS_Class() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
                
            if raw:
                print(f"[SEARCH] DuckDuckGo returned {len(raw)} results")
                return [
                    SearchResult(
                        title=r.get("title", ""),
                        snippet=r.get("body", ""),
                        url=r.get("href", ""),
                    )
                    for r in raw
                ]
        except Exception as e:
            print(f"[SEARCH] DuckDuckGo failed: {e}")
    else:
        print("[SEARCH] DuckDuckGo library not found (tried ddgs and duckduckgo_search)")

    # 2. Try Bing fallback
    try:
        print(f"[SEARCH] Trying Bing fallback...")
        results = _bing_search(query, max_results)
        if results:
            print(f"[SEARCH] Bing returned {len(results)} results")
            return results
    except Exception as e:
        print(f"[SEARCH] Bing fallback failed: {e}")
    
    print(f"[SEARCH] All search attempts failed for '{query}'")
    return []

def _bing_search(query: str, max_results: int) -> List[SearchResult]:
    """Scrape Bing search results as a robust fallback."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    # Use a slightly different URL for better results
    url = f'https://www.bing.com/search?q={requests.utils.quote(query)}&count={max_results}'
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    
    soup = BeautifulSoup(r.text, 'html.parser')
    results = []
    
    # Bing often uses 'li.b_algo' for results
    for g in soup.find_all('li', class_='b_algo'):
        if len(results) >= max_results:
            break
            
        a = g.find('a')
        # Snippet can be in different tags
        p = g.find('p') or g.find('div', class_='b_caption') or g.find('span', class_='st')
        
        if a and a.get('href'):
            title = a.text.strip()
            url = a['href']
            snippet = p.text.strip() if p else ""
            
            if title and url:
                results.append(SearchResult(title=title, snippet=snippet, url=url))
            
    return results
