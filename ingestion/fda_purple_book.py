from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


SEARCH_URL = "https://purplebooksearch.fda.gov/"


def search_biosimilars(query: str = "", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search FDA Purple Book for biosimilars."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(SEARCH_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract search form and results if available
    results: Dict[str, Any] = {
        "html": html,
        "forms_found": len(soup.find_all("form")),
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_purple_book.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/fda_purple_book")
    result = search_biosimilars(save_dir=out)
    print("Fetched FDA Purple Book data")

