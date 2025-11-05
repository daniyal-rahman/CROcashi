from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.fda.gov/drugs/drug-safety-and-availability/clinical-holds-list"


def fetch_clinical_holds(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch FDA Clinical Hold Database."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        holds = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "clinical hold" in text.lower() or "hold" in href.lower():
                holds.append({
                    "text": text[:150],
                    "href": href if href.startswith("http") else f"https://www.fda.gov{href}",
                })
        
        result = {
            "html_length": len(html),
            "holds_found": len(holds),
            "holds": holds[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "fda_clinical_hold.html", html)
            import json
            write_text(Path(save_dir) / "fda_clinical_hold.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "holds_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/fda_clinical_hold")
    result = fetch_clinical_holds(save_dir=out)
    print(f"Fetched {result.get('holds_found', 0)} clinical holds")

