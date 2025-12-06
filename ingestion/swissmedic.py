from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.swissmedic.ch"


def search_products(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search Swissmedic products database."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        products = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if any(term in text.lower() for term in ["medicament", "produit", "authorisation", "drug"]):
                products.append({
                    "text": text[:100],
                    "href": href if href.startswith("http") else f"{BASE_URL}{href}",
                })
        
        result = {
            "html_length": len(html),
            "products_found": len(products),
            "products": products[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "swissmedic.html", html)
            import json
            write_text(Path(save_dir) / "swissmedic.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "products_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/swissmedic")
    result = search_products(save_dir=out)
    print(f"Fetched {result.get('products_found', 0)} Swissmedic product references")

