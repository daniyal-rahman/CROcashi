from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.nice.org.uk/api"


def search_guidance(query: str = "biotech", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search NICE (UK) guidance and technology appraisals."""
    client = HttpClient(requests_per_second=1.0)
    # NICE may have API endpoints; using search for now
    resp = client.get(f"{API_BASE}/search", params={"q": query})
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "nice_search.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/nice_uk")
    result = search_guidance(save_dir=out)
    print("Fetched NICE UK guidance data")

