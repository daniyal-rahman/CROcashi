from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.accessdata.fda.gov/scripts/opdlisting/oopd/"


def fetch_orphan_designations(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch FDA Orphan Drug designations."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    results: Dict[str, Any] = {
        "html": html,
        "forms_found": len(soup.find_all("form")),
        "tables_found": len(soup.find_all("table")),
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_orphan.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/fda_orphan")
    result = fetch_orphan_designations(save_dir=out)
    print("Fetched FDA Orphan Drug designations")

