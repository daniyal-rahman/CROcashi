from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters"


def fetch_recent_warnings(limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch recent FDA Warning Letters."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract warning letter links
    links = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if "warning" in text.lower() or "warning" in href.lower():
            links.append({"href": href, "text": text[:100]})

    results: Dict[str, Any] = {
        "html": html,
        "links_count": len(links),
        "links": links[:limit],
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_warning_letters.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/fda_warning_letters")
    result = fetch_recent_warnings(save_dir=out)
    print(f"Fetched {result['links_count']} FDA Warning Letter references")

