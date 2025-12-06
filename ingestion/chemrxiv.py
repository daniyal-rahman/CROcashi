from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://chemrxiv.org"


def fetch_recent(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch recent ChemRxiv preprints (HTML scraping as API may not be public)."""
    client = HttpClient(requests_per_second=1.0)
    # Try to find an RSS feed or listing page
    resp = client.get(f"{BASE_URL}/engage/chemrxiv/search-dashboard")
    html = resp.text

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "chemrxiv_recent.html", html)

    soup = BeautifulSoup(html, "html.parser")
    # Basic structure extraction - adjust selectors as needed
    papers = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "/engage/chemrxiv/article-details/" in href or "/engage/chemrxiv/rss/" in href:
            papers.append({"href": href, "text": link.get_text(strip=True)})

    return {"html": html, "papers_count": len(papers), "papers": papers[:10]}


if __name__ == "__main__":
    out = Path("data/raw/chemrxiv")
    result = fetch_recent(save_dir=out)
    print(f"Fetched {result['papers_count']} ChemRxiv references")

