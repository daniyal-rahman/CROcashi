from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://string-db.org/api"


def get_interactions(identifiers: str, species: int = 9606, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Get STRING protein-protein interactions."""
    client = HttpClient(requests_per_second=2.0)
    params = {
        "identifiers": identifiers,
        "species": species,
        "format": "json",
    }
    resp = client.get(f"{API_BASE}/json/interaction_partners", params=params)
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "string_interactions.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/string_db")
    # Example: BRAF gene
    result = get_interactions("BRAF", save_dir=out)
    print("Fetched STRING DB interactions")

