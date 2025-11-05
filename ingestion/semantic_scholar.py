from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://api.semanticscholar.org/graph/v1"


def search_papers(query: str = "biotech clinical trial", limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search Semantic Scholar API."""
    client = HttpClient(requests_per_second=2.0)
    resp = client.get(
        f"{API_BASE}/paper/search",
        params={"query": query, "limit": limit, "fields": "title,authors,year,abstract"},
    )
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "semantic_scholar_search.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/semantic_scholar")
    result = search_papers(save_dir=out)
    print("Fetched Semantic Scholar data")

