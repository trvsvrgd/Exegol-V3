import os
import requests
from typing import List, Dict, Any, Optional
from duckduckgo_search import DDGS
from tools.egress_filter import EgressFilter

def search(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a web search via DuckDuckGo.
    
    Returns a list of result dictionaries with 'title', 'href', and 'body' keys.
    This is a free, no-API-key alternative to Google/Bing suitable for 
    autonomous research and evaluation tasks.
    """
    results = []
    try:
        EgressFilter.validate_request("https://duckduckgo.com")
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

def google_search(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a web search via Google Custom Search API."""
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")
    
    if not api_key or not cse_id:
        print("[web_search] Google Search skipped: API Key or CSE ID missing.")
        return []
        
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "key": api_key,
        "cx": cse_id,
        "num": num_results
    }
    
    try:
        EgressFilter.validate_request(url)
        print(f"[web_search] Querying Google: {query}")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", "No Title"),
                "href": item.get("link", "#"),
                "body": item.get("snippet", "")
            })
        return results
    except Exception as e:
        print(f"[web_search] Error during Google search: {e}")
        return []

def web_search(query: str, num_results: int = 5, provider: str = "auto") -> List[Dict[str, Any]]:
    """Unified search entry point. Defaults to Google if configured, else DuckDuckGo."""
    if provider == "google" or (provider == "auto" and os.getenv("GOOGLE_SEARCH_API_KEY")):
        results = google_search(query, num_results)
        if results: return results
    
    return search(query, num_results)

if __name__ == "__main__":
    # Quick test
    test_results = search("Exegol autonomous agent", num_results=2)
    print(f"Found {len(test_results)} results:")
    for r in test_results:
        print(f"- {r['title']} ({r['href']})")
