from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://api.reporter.nih.gov/v2"


def search_projects(query: str = "biotech", limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search NIH RePORTER for projects."""
    client = HttpClient(requests_per_second=2.0)
    payload = {
        "criteria": {
            "text_search": query,
        },
        "offset": 0,
        "limit": limit,
    }
    resp = client.session.post(
        f"{API_BASE}/Projects/Search",
        json=payload,
        headers={"Content-Type": "application/json", **client.default_headers},
        timeout=client.timeout_seconds,
    )
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "nih_reporter_projects.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/nih_reporter")
    result = search_projects(save_dir=out)
    print("Fetched NIH RePORTER projects")

