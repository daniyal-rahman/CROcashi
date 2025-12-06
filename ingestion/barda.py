from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.medicalcountermeasures.gov/barda-contracts"


def fetch_contracts(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch BARDA contracts."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        contracts = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if any(term in text.lower() for term in ["contract", "award", "barda"]):
                contracts.append({
                    "text": text[:150],
                    "href": href if href.startswith("http") else f"https://www.medicalcountermeasures.gov{href}",
                })
        
        result = {
            "html_length": len(html),
            "contracts_found": len(contracts),
            "contracts": contracts[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "barda.html", html)
            import json
            write_text(Path(save_dir) / "barda.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "contracts_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/barda")
    result = fetch_contracts(save_dir=out)
    print(f"Fetched {result.get('contracts_found', 0)} BARDA contract references")

