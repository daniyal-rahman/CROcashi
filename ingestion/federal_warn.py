from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.dol.gov/agencies/eta/layoffs/warn"


def fetch_recent_warn_notices(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch recent Federal WARN notices."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Find WARN notice links or tables
        notices = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "warn" in text.lower() or "warn" in href.lower() or "layoff" in text.lower():
                notices.append({
                    "text": text[:100],
                    "href": href,
                })
        
        result = {
            "html_length": len(html),
            "notices_found": len(notices),
            "notices": notices[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "federal_warn.html", html)
            import json
            write_text(Path(save_dir) / "federal_warn.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "notices_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/federal_warn")
    result = fetch_recent_warn_notices(save_dir=out)
    print(f"Fetched {result.get('notices_found', 0)} WARN notices")

