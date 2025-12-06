from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def search(query: str = "biotech AND clinical trial", page_size: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search Europe PMC."""
    client = HttpClient(requests_per_second=2.0)
    resp = client.get(f"{API_BASE}/search", params={"query": query, "pageSize": page_size, "format": "json"})
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "europe_pmc_search.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/europe_pmc")
    result = search(save_dir=out)
    print("Fetched Europe PMC data")

