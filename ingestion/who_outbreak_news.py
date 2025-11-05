import feedparser
from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


RSS_URL = "https://www.who.int/feeds/entity/csr/don/en/rss.xml"


def fetch_outbreak_news(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch WHO Disease Outbreak News via RSS."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(RSS_URL)
    feed = feedparser.parse(resp.text)

    result: Dict[str, Any] = {
        "title": feed.feed.get("title", ""),
        "entries_count": len(feed.entries),
        "entries": [
            {
                "title": e.get("title", ""),
                "link": e.get("link", ""),
                "published": e.get("published", ""),
                "summary": e.get("summary", "")[:200],
            }
            for e in feed.entries[:20]
        ],
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "who_outbreak_news.xml", resp.text)
        import json

        write_text(Path(save_dir) / "who_outbreak_news.json", json.dumps(result, indent=2))

    return result


if __name__ == "__main__":
    out = Path("data/raw/who_outbreak_news")
    result = fetch_outbreak_news(save_dir=out)
    print(f"Fetched {result['entries_count']} WHO outbreak news items")

