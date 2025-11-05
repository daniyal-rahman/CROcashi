from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://api.biorxiv.org/details/medrxiv"


def fetch_range(start: date, end: date, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    client = HttpClient(requests_per_second=2.0)
    url = f"{API_BASE}/{start.isoformat()}/{end.isoformat()}"
    resp = client.get(url)
    data = client.json_or_text(resp)
    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / f"medrxiv_{start.isoformat()}_{end.isoformat()}.json", resp.text)
    return data  # type: ignore[return-value]


def fetch_recent(days: int = 1, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    end = date.today()
    start = end - timedelta(days=days)
    return fetch_range(start, end, save_dir=save_dir)


if __name__ == "__main__":
    out = Path("data/raw/medrxiv")
    data = fetch_recent(save_dir=out)
    print(f"Fetched {len(data.get('collection', []))} medRxiv records (recent)")


