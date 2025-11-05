from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.fda.gov/regulatory-information/search-fda-guidance-documents"


def search_guidance(query: str = "", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search FDA Guidance Documents."""
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL, params={"search": query} if query else None)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract guidance document links
    links = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if "guidance" in text.lower() or "guidance" in href.lower():
            links.append({"href": href, "text": text[:150]})

    results: Dict[str, Any] = {
        "html": html,
        "links_count": len(links),
        "links": links[:50],
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_guidance.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/fda_guidance")
    result = search_guidance(save_dir=out)
    print(f"Fetched {result['links_count']} FDA guidance references")

