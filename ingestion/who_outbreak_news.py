import feedparser
from pathlib import Path
from typing import Any, Dict, Optional, List

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


RSS_URL = "https://www.who.int/feeds/entity/csr/don/en/rss.xml"


def fetch_outbreak_news(
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch WHO Disease Outbreak News via RSS.
    
    Args:
        limit: Maximum number of entries to fetch
        save_dir: Optional directory to save raw XML/JSON
        load_to_staging: Whether to load data into staging table
    """
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(RSS_URL)
    feed = feedparser.parse(resp.text)

    entries = []
    for e in feed.entries[:limit]:
        entries.append({
            "title": e.get("title", ""),
            "link": e.get("link", ""),
            "published": e.get("published", ""),
            "summary": e.get("summary", "")[:2000],
        })

    result: Dict[str, Any] = {
        "title": feed.feed.get("title", ""),
        "entries_count": len(entries),
        "entries": entries,
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "who_outbreak_news.xml", resp.text)
        import json
        write_text(Path(save_dir) / "who_outbreak_news.json", json.dumps(result, indent=2, default=str))

    # Load to staging if requested
    if load_to_staging and entries:
        loader = StagingLoader('who_outbreak_news')
        stats = loader.load_records(
            entries,
            id_extractor=lambda r: r.get('link') or r.get('title', '')[:100],
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        result['staging_stats'] = stats

    return result


if __name__ == "__main__":
    out = Path("data/raw/who_outbreak_news")
    result = fetch_outbreak_news(save_dir=out)
    print(f"Fetched {result['entries_count']} WHO outbreak news items")

