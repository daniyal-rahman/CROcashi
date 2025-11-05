import feedparser
from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


def fetch_biotech_news(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch Google News biotech articles via RSS."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    # Google News RSS for biotech
    rss_url = "https://news.google.com/rss/search?q=biotech+OR+pharmaceutical+OR+clinical+trial&hl=en-US&gl=US&ceid=US:en"
    
    try:
        resp = client.get(rss_url)
        feed = feedparser.parse(resp.text)
        
        entries = [
            {
                "title": e.get("title", ""),
                "link": e.get("link", ""),
                "published": e.get("published", ""),
                "source": e.get("source", {}).get("title", "") if e.get("source") else "",
            }
            for e in feed.entries[:30]
        ]
        
        result = {
            "feed_title": feed.feed.get("title", ""),
            "entries_count": len(entries),
            "entries": entries,
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            import json
            write_text(Path(save_dir) / "google_news.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "entries_count": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/google_news")
    result = fetch_biotech_news(save_dir=out)
    print(f"Fetched {result.get('entries_count', 0)} Google News articles")

