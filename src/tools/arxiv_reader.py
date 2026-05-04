import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from tools.egress_filter import EgressFilter

def search_arxiv(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a search on arXiv using their public API.
    
    Returns a list of result dictionaries with 'id', 'title', 'summary', 'published', 'authors', and 'link'.
    """
    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending"
    }
    
    try:
        EgressFilter.validate_request(base_url)
        print(f"[arxiv_reader] Querying arXiv: {query}")
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        
        # Parse XML (Atom format)
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        entries = []
        for entry in root.findall('atom:entry', ns):
            paper_id = entry.find('atom:id', ns).text
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
            published = entry.find('atom:published', ns).text
            authors = [a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)]
            
            # Find the PDF link if available
            pdf_link = paper_id
            for link in entry.findall('atom:link', ns):
                if link.attrib.get('title') == 'pdf':
                    pdf_link = link.attrib.get('href')
                    break
                    
            entries.append({
                "id": paper_id,
                "title": title,
                "summary": summary,
                "published": published,
                "authors": authors,
                "link": pdf_link
            })
            
        return entries
    except Exception as e:
        print(f"[arxiv_reader] Error during arXiv search: {e}")
        return []

def get_paper_by_id(paper_id: str) -> Optional[Dict[str, Any]]:
    """Fetches details for a specific arXiv paper ID."""
    # paper_id can be '2103.12345' or full URL
    if "abs/" in paper_id:
        paper_id = paper_id.split("abs/")[-1]
    
    base_url = "http://export.arxiv.org/api/query"
    params = {
        "id_list": paper_id
    }
    
    try:
        EgressFilter.validate_request(base_url)
        print(f"[arxiv_reader] Fetching paper ID: {paper_id}")
        response = requests.get(base_url, params=params, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        entry = root.find('atom:entry', ns)
        if entry is not None:
            title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
            summary = entry.find('atom:summary', ns).text.strip().replace('\n', ' ')
            published = entry.find('atom:published', ns).text
            authors = [a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)]
            
            pdf_link = paper_id
            for link in entry.findall('atom:link', ns):
                if link.attrib.get('title') == 'pdf':
                    pdf_link = link.attrib.get('href')
                    break
                    
            return {
                "id": entry.find('atom:id', ns).text,
                "title": title,
                "summary": summary,
                "published": published,
                "authors": authors,
                "link": pdf_link
            }
        return None
    except Exception as e:
        print(f"[arxiv_reader] Error fetching paper {paper_id}: {e}")
        return None

if __name__ == "__main__":
    # Test
    res = search_arxiv("agentic evaluation", max_results=1)
    if res:
        print(f"Found: {res[0]['title']}")
    else:
        print("No results found.")
