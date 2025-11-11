from pathlib import Path
from typing import Any, Dict, Optional, List

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.hsa.gov.sg"


def search_products(
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """Search HSA (Singapore) products database."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        products = []
        records = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if any(term in text.lower() for term in ["therapeutic", "product", "medicine", "register"]):
                full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                products.append({
                    "text": text[:100],
                    "href": full_url,
                })
                records.append({
                    'product_name': text[:200],
                    'url': full_url,
                    'text': text[:500],
                    'raw_text': text
                })
        
        result = {
            "html_length": len(html),
            "products_found": len(products),
            "products": products[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "hsa_singapore.html", html)
            import json
            write_text(Path(save_dir) / "hsa_singapore.json", json.dumps(result, indent=2))
        
        stats = {'parsed': len(records), 'inserted': 0, 'skipped': 0, 'errors': 0}
        
        if load_to_staging and records:
            loader = StagingLoader('hsa_singapore')
            staging_stats = loader.load_records(
                records,
                id_extractor=lambda r: r.get('url') or r.get('product_name', '')[:100] or '',
                skip_duplicates=True
            )
            stats.update(staging_stats)
            print(f"Staging: {staging_stats['inserted']} inserted, {staging_stats['skipped']} skipped, {staging_stats['errors']} errors")
        
        result.update(stats)
        return result
    except Exception as e:
        return {
            "products_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/hsa_singapore")
    result = search_products(save_dir=out)
    print(f"Fetched {result.get('products_found', 0)} HSA product references")

