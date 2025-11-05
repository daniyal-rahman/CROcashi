from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "http://web.archive.org/cdx/search/cdx"


def get_snapshots(url: str, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Get Wayback Machine snapshots for a URL."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(API_BASE, params={"url": url, "output": "json", "limit": 50})
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        safe_name = url.replace("/", "_").replace(":", "_")[:50]
        write_text(Path(save_dir) / f"wayback_{safe_name}.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/wayback_machine")
    result = get_snapshots("fda.gov", save_dir=out)
    print("Fetched Wayback Machine snapshots")

