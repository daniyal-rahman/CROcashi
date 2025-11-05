from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://portal.uspto.gov/pair/PublicPair"


def search_application(app_number: str, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search USPTO Public PAIR for patent application."""
    client = HttpClient(requests_per_second=1.0)
    # Note: Public PAIR requires form submission; this is a basic structure
    resp = client.get(BASE_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    results: Dict[str, Any] = {
        "html": html,
        "forms_found": len(soup.find_all("form")),
        "note": "Public PAIR requires form-based search; manual implementation needed",
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "uspto_public_pair.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/uspto_public_pair")
    result = search_application("", save_dir=out)
    print("Fetched USPTO Public PAIR structure")

