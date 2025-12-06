from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def esearch_clinvar(term: str = "cancer", retmax: int = 50, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Search ClinVar using E-utilities."""
    client = HttpClient(requests_per_second=10.0 if api_key else 3.0)
    params = {
        "db": "clinvar",
        "term": term,
        "retmax": retmax,
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key
    resp = client.get(f"{API_BASE}/esearch.fcgi", params=params)
    data = client.json_or_text(resp)

    return data  # type: ignore[return-value]


def fetch_sample(term: str = "biotech", retmax: int = 50, api_key: Optional[str] = None, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch sample ClinVar data."""
    data = esearch_clinvar(term=term, retmax=retmax, api_key=api_key)

    if save_dir is not None:
        ensure_dir(save_dir)
        import json

        write_text(Path(save_dir) / "clinvar_search.json", json.dumps(data, indent=2))

    return data


if __name__ == "__main__":
    out = Path("data/raw/clinvar")
    result = fetch_sample(save_dir=out)
    print("Fetched ClinVar data")

