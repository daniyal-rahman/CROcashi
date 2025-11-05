from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


# Note: YouTube Data API requires API key, but we can try RSS feeds
RSS_BASE = "https://www.youtube.com/feeds/videos.xml"


def fetch_channel_videos(channel_id: str = "UCBi2mrWuNuyYy4gbM6fU18Q", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch YouTube videos from a biotech channel via RSS."""
    import feedparser
    
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    # YouTube RSS feed format
    rss_url = f"{RSS_BASE}?channel_id={channel_id}"
    
    try:
        resp = client.get(rss_url)
        feed = feedparser.parse(resp.text)
        
        videos = [
            {
                "title": e.get("title", ""),
                "link": e.get("link", ""),
                "published": e.get("published", ""),
            }
            for e in feed.entries[:20]
        ]
        
        result = {
            "channel_title": feed.feed.get("title", ""),
            "videos_count": len(videos),
            "videos": videos,
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            import json
            write_text(Path(save_dir) / "youtube_biotech.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "videos_count": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/youtube_biotech")
    result = fetch_channel_videos(save_dir=out)
    print(f"Fetched {result.get('videos_count', 0)} YouTube videos")

