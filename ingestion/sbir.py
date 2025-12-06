from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.sbir.gov/"


def search_awards(query: str = "", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search SBIR/STTR awards database."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    results: Dict[str, Any] = {
        "html": html,
        "search_available": "search" in html.lower() or "award" in html.lower(),
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "sbir.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/sbir")
    result = search_awards(save_dir=out)
    print("Fetched SBIR/STTR structure")

