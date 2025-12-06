from pathlib import Path
from typing import Any, Dict, Optional, List

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.fda.gov/regulatory-information/search-fda-guidance-documents"


def search_guidance(
    query: str = "",
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """Search FDA Guidance Documents."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL, params={"search": query} if query else None)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract guidance document links
    links = []
    records = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if "guidance" in text.lower() or "guidance" in href.lower():
            full_url = href if href.startswith("http") else f"https://www.fda.gov{href}"
            links.append({"href": href, "text": text[:150]})
            records.append({
                'title': text[:200],
                'url': full_url,
                'text': text[:500],
                'raw_text': text
            })

    results: Dict[str, Any] = {
        "html": html,
        "links_count": len(links),
        "links": links[:50],
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_guidance.html", html)

    stats = {'parsed': len(records), 'inserted': 0, 'skipped': 0, 'errors': 0}
    
    if load_to_staging and records:
        loader = StagingLoader('fda_guidance')
        
        def guidance_id_extractor(r):
            # Use full URL if unique, otherwise hash title
            url = r.get('url', '')
            title = r.get('title', '') or r.get('text', '')
            
            # If URL is unique (not the base search page), use it
            if url and url != BASE_URL and len(url) > len(BASE_URL) + 10:
                return url
            
            # Fallback: hash of title for uniqueness
            from src.utils.id_generation import generate_hash_id
            if title:
                return generate_hash_id('FDA-GUIDANCE', title, url)
            return url or ''
        
        staging_stats = loader.load_records(
            records,
            id_extractor=guidance_id_extractor,
            skip_duplicates=True
        )
        stats.update(staging_stats)
        print(f"Staging: {staging_stats['inserted']} inserted, {staging_stats['skipped']} skipped, {staging_stats['errors']} errors")
    
    results.update(stats)
    return results


if __name__ == "__main__":
    out = Path("data/raw/fda_guidance")
    result = search_guidance(save_dir=out)
    print(f"Fetched {result['links_count']} FDA guidance references")

