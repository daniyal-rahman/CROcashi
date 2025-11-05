from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.twc.texas.gov/businesses/warn-notices"


def fetch_recent_warn_notices(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch recent Texas WARN notices."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        notices = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "warn" in text.lower() or "warn" in href.lower():
                notices.append({
                    "text": text[:100],
                    "href": href if href.startswith("http") else f"https://www.twc.texas.gov{href}",
                })
        
        result = {
            "html_length": len(html),
            "notices_found": len(notices),
            "notices": notices[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "texas_warn.html", html)
            import json
            write_text(Path(save_dir) / "texas_warn.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "notices_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/texas_warn")
    result = fetch_recent_warn_notices(save_dir=out)
    print(f"Fetched {result.get('notices_found', 0)} Texas WARN notices")

