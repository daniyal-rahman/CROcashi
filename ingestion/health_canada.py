from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://health-products.canada.ca/dpd-bdpp/"


def parse_product_entry(entry_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse individual product entry to extract structured data."""
    parsed = {
        'din': entry_data.get('din') or entry_data.get('id', ''),
        'product_name': entry_data.get('product_name') or entry_data.get('name', ''),
        'company_name': entry_data.get('company_name') or entry_data.get('manufacturer', ''),
        'approval_date': entry_data.get('approval_date') or entry_data.get('date', ''),
    }
    return parsed


def search_products(
    query: str = "",
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Search Health Canada Drug Product Database.
    
    Args:
        query: Search query
        limit: Maximum number of results
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table
    """
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL, params={"lang": "en"})
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    parsed_products = []
    
    # Look for product entries in HTML
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        href = link.get("href", "")
        if "product" in href.lower() or "din" in href.lower():
            if text and len(text) > 5:
                parsed = {
                    'product_name': text,
                    'url': href if href.startswith("http") else f"{BASE_URL.rstrip('/')}{href}",
                }
                parsed_products.append(parsed)
                if len(parsed_products) >= limit:
                    break

    results: Dict[str, Any] = {
        "html_length": len(html),
        "forms_found": len(soup.find_all("form")),
        "search_available": "search" in html.lower(),
        "products_found": len(parsed_products),
        "products": parsed_products,
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "health_canada.html", html)
        import json
        if parsed_products:
            write_text(Path(save_dir) / "health_canada.json", json.dumps(results, indent=2, default=str))

    # Load to staging if requested
    if load_to_staging and parsed_products:
        loader = StagingLoader('health_canada')
        stats = loader.load_records(
            parsed_products,
            id_extractor=lambda r: r.get('din') or r.get('product_name', '')[:100],
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        results['staging_stats'] = stats

    return results


if __name__ == "__main__":
    out = Path("data/raw/health_canada")
    result = search_products(save_dir=out)
    print("Fetched Health Canada DPD-BDPP structure")

