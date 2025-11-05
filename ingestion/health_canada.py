from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://health-products.canada.ca/dpd-bdpp/"


def search_products(query: str = "", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search Health Canada Drug Product Database."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL, params={"lang": "en"})
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    results: Dict[str, Any] = {
        "html": html,
        "forms_found": len(soup.find_all("form")),
        "search_available": "search" in html.lower(),
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "health_canada.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/health_canada")
    result = search_products(save_dir=out)
    print("Fetched Health Canada DPD-BDPP structure")

