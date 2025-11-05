from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.fda.gov/drugs/nda-and-bla-approvals/breakthrough-therapy"


def scrape_designations(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Scrape FDA Breakthrough Therapy designations."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract tables or lists of designations
    tables = soup.find_all("table")
    results: Dict[str, Any] = {
        "html": html,
        "tables_count": len(tables),
        "links": [a.get("href", "") for a in soup.find_all("a", href=True) if "breakthrough" in a.get("href", "").lower()],
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_breakthrough.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/fda_breakthrough")
    result = scrape_designations(save_dir=out)
    print("Fetched FDA Breakthrough Therapy designations")

