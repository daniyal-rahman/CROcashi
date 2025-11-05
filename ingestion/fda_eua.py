from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.fda.gov/emergency-preparedness-and-response/mcm-legal-regulatory-and-policy-framework/emergency-use-authorization"


def fetch_recent_euas(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch FDA Emergency Use Authorizations."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Find EUA links
        euas = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "eua" in text.lower() or "eua" in href.lower() or "emergency use" in text.lower():
                euas.append({
                    "text": text[:150],
                    "href": href if href.startswith("http") else f"https://www.fda.gov{href}",
                })
        
        result = {
            "html_length": len(html),
            "euas_found": len(euas),
            "euas": euas[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "fda_eua.html", html)
            import json
            write_text(Path(save_dir) / "fda_eua.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "euas_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/fda_eua")
    result = fetch_recent_euas(save_dir=out)
    print(f"Fetched {result.get('euas_found', 0)} EUAs")

