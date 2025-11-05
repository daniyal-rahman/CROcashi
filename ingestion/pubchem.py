from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


def get_compound(cid: str, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Get PubChem compound by CID."""
    client = HttpClient(requests_per_second=2.0)
    resp = client.get(f"{API_BASE}/compound/cid/{cid}/JSON")
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / f"pubchem_cid_{cid}.json", resp.text)

    return data  # type: ignore[return-value]


def search_substance(query: str, limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search PubChem substances."""
    client = HttpClient(requests_per_second=2.0)
    resp = client.get(f"{API_BASE}/substance/name/{query}/JSON")
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / f"pubchem_substance_{query}.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/pubchem")
    # Example: aspirin CID = 2244
    result = get_compound("2244", save_dir=out)
    print("Fetched PubChem compound data")

