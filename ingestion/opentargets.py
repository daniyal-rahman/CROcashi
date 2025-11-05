from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://api.platform.opentargets.org/api/v4"


def search_targets(query: str = "BRAF", limit: int = 10, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search OpenTargets using GraphQL."""
    client = HttpClient(requests_per_second=1.0)  # Rate limit: be polite
    query_str = """
    query searchTargets($query: String!) {
        search(queryString: $query) {
            hits {
                id
                name
            }
        }
    }
    """
    payload = {"query": query_str, "variables": {"query": query}}
    resp = client.session.post(
        f"{API_BASE}/graphql", json=payload, headers={"Content-Type": "application/json", **client.default_headers}, timeout=client.timeout_seconds
    )
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "opentargets_search.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/opentargets")
    result = search_targets(save_dir=out)
    print("Fetched OpenTargets data")

