from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.ema.europa.eu/en/human-regulatory/research-development/prime-priority-medicines"


def fetch_prime_designations(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch EMA PRIME designations."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Find PRIME designation links or tables
        designations = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "prime" in text.lower() or "prime" in href.lower():
                designations.append({
                    "text": text[:150],
                    "href": href if href.startswith("http") else f"https://www.ema.europa.eu{href}",
                })
        
        result = {
            "html_length": len(html),
            "designations_found": len(designations),
            "designations": designations[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "ema_prime.html", html)
            import json
            write_text(Path(save_dir) / "ema_prime.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "designations_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/ema_prime")
    result = fetch_prime_designations(save_dir=out)
    print(f"Fetched {result.get('designations_found', 0)} PRIME designations")

