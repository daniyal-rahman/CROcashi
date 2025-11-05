from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://products.mhra.gov.uk/"


def search_products(query: str = "", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search UK MHRA product database."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    results: Dict[str, Any] = {
        "html": html,
        "forms_found": len(soup.find_all("form")),
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "mhra_uk.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/mhra_uk")
    result = search_products(save_dir=out)
    print("Fetched UK MHRA data")

