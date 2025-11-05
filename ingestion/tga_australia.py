from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.tga.gov.au/products/medicines"


def search_medicines(query: str = "", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search TGA (Australia) medicines database."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        if resp.status_code != 200:
            return {
                "medicines_found": 0,
                "error": f"HTTP {resp.status_code}",
                "html_length": 0,
            }
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Find medicine links or search forms
        medicines = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if any(term in text.lower() for term in ["medicine", "product", "register", "artg"]):
                medicines.append({
                    "text": text[:100],
                    "href": href if href.startswith("http") else f"https://www.tga.gov.au{href}",
                })
        
        result = {
            "html_length": len(html),
            "medicines_found": len(medicines),
            "medicines": medicines[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "tga_australia.html", html)
            import json
            write_text(Path(save_dir) / "tga_australia.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "medicines_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/tga_australia")
    result = search_medicines(save_dir=out)
    print(f"Fetched {result.get('medicines_found', 0)} TGA medicine references")

