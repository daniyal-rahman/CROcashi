from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://rest.uniprot.org"


def search_proteins(query: str = "cancer AND reviewed:true", limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search UniProt proteins."""
    client = HttpClient(requests_per_second=2.0)
    resp = client.get(f"{API_BASE}/uniprotkb/search", params={"query": query, "format": "json", "size": limit})
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "uniprot_search.json", resp.text)

    return data  # type: ignore[return-value]


def get_protein(accession: str, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Get UniProt protein by accession."""
    client = HttpClient(requests_per_second=2.0)
    resp = client.get(f"{API_BASE}/uniprotkb/{accession}.json")
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / f"uniprot_{accession}.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/uniprot")
    result = search_proteins(save_dir=out)
    print("Fetched UniProt data")

