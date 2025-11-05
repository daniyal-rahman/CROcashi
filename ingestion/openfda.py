from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://api.fda.gov"


def search_drugs(query: str = "*", limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search OpenFDA drug endpoint."""
    client = HttpClient(requests_per_second=2.0)
    params = {"search": query, "limit": limit}
    resp = client.get(f"{API_BASE}/drug/label.json", params=params)
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "openfda_drugs.json", resp.text)

    return data  # type: ignore[return-value]


def search_devices(query: str = "*", limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search OpenFDA device endpoint."""
    client = HttpClient(requests_per_second=2.0)
    params = {"search": query, "limit": limit}
    resp = client.get(f"{API_BASE}/device/510k.json", params=params)
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "openfda_devices.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/openfda")
    drugs = search_drugs(save_dir=out)
    devices = search_devices(save_dir=out)
    print("Fetched OpenFDA data")

