from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://webservice.thebiogrid.org"


def get_interactions(gene_symbol: str = "BRAF", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Get BioGRID protein interactions."""
    client = HttpClient(requests_per_second=2.0)
    params = {
        "geneList": gene_symbol,
        "accessKey": "",  # Optional access key for higher limits
        "format": "json",
    }
    resp = client.get(f"{API_BASE}/interactions", params=params)
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / f"biogrid_{gene_symbol}.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/biogrid")
    result = get_interactions(save_dir=out)
    print("Fetched BioGRID interactions")

