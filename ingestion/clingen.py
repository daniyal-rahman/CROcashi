from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://reg.clinicalgenome.org/alleles"


def search_alleles(query: str = "", limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search ClinGen Allele Registry."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    # ClinGen may have REST API endpoints
    resp = client.get(f"{API_BASE}/search", params={"q": query, "limit": limit})
    data = client.json_or_text(resp)
    
    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "clingen_search.json", resp.text)
    
    return data  # type: ignore[return-value]


def get_clingen_data(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Get ClinGen data (try alternative endpoint if search doesn't work)."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    # Try main ClinGen site
    resp = client.get("https://www.clinicalgenome.org/")
    html = resp.text
    
    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "clingen.html", html)
    
    return {"html_length": len(html), "note": "ClinGen main page"}


if __name__ == "__main__":
    out = Path("data/raw/clingen")
    result = get_clingen_data(save_dir=out)
    print("Fetched ClinGen data")

