from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.disgenet.org/api"


def search_diseases(query: str = "cancer", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search DisGeNET disease-gene associations."""
    client = HttpClient(requests_per_second=1.0)
    # Note: DisGeNET API may require authentication; check actual endpoint
    resp = client.get(f"{API_BASE}/gda/disease/{query}")
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "disgenet_search.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/disgenet")
    result = search_diseases(save_dir=out)
    print("Fetched DisGeNET data")

