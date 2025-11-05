import feedparser
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


RSS_FEEDS = {
    "endpoints": "https://endpts.com/feed/",
    "fiercebiotech": "https://www.fiercebiotech.com/rss/xml",
    "biopharmadive": "https://www.biopharmadive.com/feeds/news/",
    "biospace": "https://www.biospace.com/news/rss/",
    "stat": "https://www.statnews.com/feed/",
    "genomeweb": "https://www.genomeweb.com/rss.xml",
    "pmlive": "https://www.pmlive.com/rss",
    "bioworld": "https://www.bioworld.com/rss",
    "gen_news": "https://www.genengnews.com/feed/",
    "xconomy": "https://xconomy.com/feed/",
    "medcitynews": "https://medcitynews.com/feed/",
    "pharmavoice": "https://www.pharmavoice.com/feed/",
}


def fetch_feed(name: str, url: Optional[str] = None, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch and parse an RSS feed."""
    if url is None:
        url = RSS_FEEDS.get(name)
        if url is None:
            raise ValueError(f"Unknown feed: {name}")

    client = HttpClient(requests_per_second=1.0)
    resp = client.get(url)
    feed = feedparser.parse(resp.text)

    result: Dict[str, Any] = {
        "title": feed.feed.get("title", ""),
        "entries_count": len(feed.entries),
        "entries": [{"title": e.get("title", ""), "link": e.get("link", ""), "published": e.get("published", "")} for e in feed.entries[:20]],
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / f"{name}_feed.xml", resp.text)
        import json

        write_text(Path(save_dir) / f"{name}_feed.json", json.dumps(result, indent=2))

    return result


def fetch_all_feeds(save_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Fetch all configured RSS feeds."""
    results = {}
    for name in RSS_FEEDS:
        try:
            results[name] = fetch_feed(name, save_dir=save_dir)
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


if __name__ == "__main__":
    out = Path("data/raw/rss_news")
    all_feeds = fetch_all_feeds(save_dir=out)
    print(f"Fetched {len([k for k, v in all_feeds.items() if 'error' not in v])} RSS feeds")

