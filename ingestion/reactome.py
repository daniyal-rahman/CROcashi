from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://reactome.org/ContentService"


def search_pathways(query: str = "cancer", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search Reactome pathways."""
    client = HttpClient(requests_per_second=2.0)
    resp = client.get(f"{API_BASE}/search/query", params={"query": query, "cluster": "true"})
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "reactome_search.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/reactome")
    result = search_pathways(save_dir=out)
    print("Fetched Reactome pathways")

