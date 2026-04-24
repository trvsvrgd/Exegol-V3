import os
from typing import List, Dict, Any, Optional
from duckduckgo_search import DDGS

def search(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a web search via DuckDuckGo.
    
    Returns a list of result dictionaries with 'title', 'href', and 'body' keys.
    This is a free, no-API-key alternative to Google/Bing suitable for 
    autonomous research and evaluation tasks.
    """
    results = []
    try:
        print(f"[web_search] Querying DuckDuckGo: {query}")
        with DDGS() as ddgs:
            # text() returns an iterator of results
            ddgs_results = list(ddgs.text(query, max_results=num_results))
            for r in ddgs_results:
                results.append({
                    "title": r.get("title", "No Title"),
                    "href": r.get("href", "#"),
                    "body": r.get("body", "")
                })
        return results
    except Exception as e:
        print(f"[web_search] Error during DuckDuckGo search: {e}")
        return []

def search_news(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a news search via DuckDuckGo."""
    results = []
    try:
        with DDGS() as ddgs:
            ddgs_results = list(ddgs.news(query, max_results=num_results))
            for r in ddgs_results:
                results.append({
                    "date": r.get("date"),
                    "title": r.get("title"),
                    "body": r.get("body"),
                    "url": r.get("url")
                })
        return results
    except Exception as e:
        print(f"[web_search] Error during DuckDuckGo news search: {e}")
        return []

if __name__ == "__main__":
    # Quick test
    test_results = search("Exegol autonomous agent", num_results=2)
    print(f"Found {len(test_results)} results:")
    for r in test_results:
        print(f"- {r['title']} ({r['href']})")
