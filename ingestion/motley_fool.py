import feedparser
from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


def fetch_biotech_articles(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch Motley Fool biotech articles via RSS."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    # Try biotech/healthcare RSS feeds
    rss_urls = [
        "https://www.fool.com/feeds/index.aspx",
        "https://www.fool.com/tag/biotech/feed/",
    ]
    
    all_entries = []
    for url in rss_urls:
        try:
            resp = client.get(url)
            feed = feedparser.parse(resp.text)
            
            if feed.entries:
                all_entries.extend([
                    {
                        "title": e.get("title", ""),
                        "link": e.get("link", ""),
                        "published": e.get("published", ""),
                    }
                    for e in feed.entries[:20]
                ])
        except Exception:
            continue
    
    result = {
        "entries_count": len(all_entries),
        "entries": all_entries[:20],
    }
    
    if save_dir is not None:
        ensure_dir(save_dir)
        import json
        write_text(Path(save_dir) / "motley_fool.json", json.dumps(result, indent=2))
    
    return result


if __name__ == "__main__":
    out = Path("data/raw/motley_fool")
    result = fetch_biotech_articles(save_dir=out)
    print(f"Fetched {result['entries_count']} Motley Fool articles")

