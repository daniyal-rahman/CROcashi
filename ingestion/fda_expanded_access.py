from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.fda.gov/news-events/public-health-focus/expanded-access-compassionate-use"


def fetch_expanded_access(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch FDA Expanded Access (Compassionate Use) information."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Find expanded access links
        links_found = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if any(term in text.lower() for term in ["expanded access", "compassionate", "eIND", "eIND"]):
                links_found.append({
                    "text": text[:150],
                    "href": href if href.startswith("http") else f"https://www.fda.gov{href}",
                })
        
        result = {
            "html_length": len(html),
            "links_found": len(links_found),
            "links": links_found[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "fda_expanded_access.html", html)
            import json
            write_text(Path(save_dir) / "fda_expanded_access.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "links_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/fda_expanded_access")
    result = fetch_expanded_access(save_dir=out)
    print(f"Fetched {result.get('links_found', 0)} expanded access links")

