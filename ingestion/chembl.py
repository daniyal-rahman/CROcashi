from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.ebi.ac.uk/chembl/api/data"


def get_compounds(limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch ChEMBL compounds."""
    client = HttpClient(requests_per_second=2.0)
    resp = client.get(f"{API_BASE}/compound.json", params={"limit": limit})
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "chembl_compounds.json", resp.text)

    return data  # type: ignore[return-value]


def search_activities(query: str = "cancer", limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search ChEMBL bioactivities."""
    client = HttpClient(requests_per_second=2.0)
    # Note: ChEMBL uses different endpoints; adjust as needed
    resp = client.get(f"{API_BASE}/activity.json", params={"limit": limit})
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "chembl_activities.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/chembl")
    compounds = get_compounds(save_dir=out)
    print("Fetched ChEMBL data")

