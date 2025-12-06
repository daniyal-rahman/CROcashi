from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.tga.gov.au/products/medicines"


def parse_medicine_entry(entry_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse individual medicine entry to extract structured data."""
    parsed = {
        'artg_id': entry_data.get('artg_id') or entry_data.get('id', ''),
        'product_name': entry_data.get('product_name') or entry_data.get('name', ''),
        'company_name': entry_data.get('company_name') or entry_data.get('sponsor', ''),
        'approval_date': entry_data.get('approval_date') or entry_data.get('date', ''),
    }
    return parsed


def search_medicines(
    query: str = "",
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Search TGA (Australia) medicines database.
    
    Args:
        query: Search query
        limit: Maximum number of results
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table
    """
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
        
        parsed_medicines = []
        
        # Find medicine links or search forms
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if any(term in text.lower() for term in ["medicine", "product", "register", "artg"]):
                parsed = {
                    'product_name': text,
                    'url': href if href.startswith("http") else f"https://www.tga.gov.au{href}",
                }
                parsed_medicines.append(parsed)
                if len(parsed_medicines) >= limit:
                    break
        
        result = {
            "html_length": len(html),
            "medicines_found": len(parsed_medicines),
            "medicines": parsed_medicines,
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "tga_australia.html", html)
            import json
            write_text(Path(save_dir) / "tga_australia.json", json.dumps(result, indent=2, default=str))
        
        # Load to staging if requested
        if load_to_staging and parsed_medicines:
            loader = StagingLoader('tga_australia')
            stats = loader.load_records(
                parsed_medicines,
                id_extractor=lambda r: r.get('artg_id') or r.get('product_name', '')[:100],
                skip_duplicates=True
            )
            print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
            result['staging_stats'] = stats
        
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

