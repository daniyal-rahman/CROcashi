from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.ncbi.nlm.nih.gov/research/pubtator3/api"


def search_annotations(query: str = "cancer", limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search PubTator 3.0 for annotations."""
    client = HttpClient(requests_per_second=2.0)
    # PubTator uses different endpoints; adjust based on actual API
    resp = client.get(f"{API_BASE}/search", params={"query": query, "limit": limit})
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "pubtator_search.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/pubtator")
    result = search_annotations(save_dir=out)
    print("Fetched PubTator data")

