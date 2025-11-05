from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.reddit.com/r/biotech"


def fetch_recent(limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch recent posts from r/biotech."""
    client = HttpClient(requests_per_second=1.0, user_agent="CROcashi-Ingestion/1.0")
    resp = client.get(f"{API_BASE}/new.json", params={"limit": limit})
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "reddit_biotech.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/reddit_biotech")
    result = fetch_recent(save_dir=out)
    print("Fetched r/biotech data")

