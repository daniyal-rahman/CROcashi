from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://api.patentsview.org/patents/query"


def search_patents(query: str = '{"_gte":{"patent_date":"2020-01-01"}}', limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search USPTO PatentsView API."""
    client = HttpClient(requests_per_second=2.0)
    params = {
        "q": query,
        "f": '["patent_number","patent_date","assignee_organization","title"]',
        "o": {"per_page": limit, "page": 1},
    }
    resp = client.session.post(API_BASE, json=params, headers={"Content-Type": "application/json", **client.default_headers}, timeout=client.timeout_seconds)
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "patentsview_search.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/patentsview")
    result = search_patents(save_dir=out)
    print("Fetched PatentsView data")

