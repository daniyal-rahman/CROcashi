from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


API_BASE = "https://www.ema.europa.eu/en/medicines"


def parse_epar_entry(entry_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse individual EPAR entry to extract structured data."""
    parsed = {
        'epar_id': entry_data.get('epar_id') or entry_data.get('id', ''),
        'medicine_name': entry_data.get('medicine_name') or entry_data.get('name', ''),
        'marketing_authorization_holder': entry_data.get('marketing_authorization_holder') or entry_data.get('company_name', ''),
        'approval_date': entry_data.get('approval_date') or entry_data.get('date', ''),
        'additional_info': entry_data.get('description', '')
    }
    return parsed


def search_medicines(
    query: str = "",
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Search EMA Product Database (EPAR).
    
    Args:
        query: Search query
        limit: Maximum number of results
        save_dir: Optional directory to save raw data
        load_to_staging: Whether to load data into staging table
    """
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(API_BASE, params={"search": query} if query else None)
    html = resp.text

    import json
    parsed_entries = []
    
    # Try to parse as JSON
    try:
        data = json.loads(html)
        is_json = True
        
        # Extract entries from JSON response
        entries = data.get('results', []) or data.get('medicines', []) or []
        for entry in entries[:limit]:
            parsed = parse_epar_entry(entry)
            if parsed['epar_id'] or parsed['medicine_name']:
                parsed_entries.append(parsed)
    except json.JSONDecodeError:
        is_json = False
        # Parse HTML
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for medicine entries in HTML
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if "medicine" in href.lower() or "epar" in href.lower():
                if text and len(text) > 5:
                    parsed = {
                        'epar_id': href.split('/')[-1] if '/' in href else '',
                        'medicine_name': text,
                        'url': href if href.startswith("http") else f"https://www.ema.europa.eu{href}",
                    }
                    parsed_entries.append(parsed)
                    if len(parsed_entries) >= limit:
                        break

    results: Dict[str, Any] = {
        "is_json": is_json,
        "parsed_entries": len(parsed_entries),
        "entries": parsed_entries,
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        if is_json:
            write_text(Path(save_dir) / "ema_epar_search.json", json.dumps(results, indent=2, default=str))
        else:
            write_text(Path(save_dir) / "ema_epar_search.html", html)

    # Load to staging if requested
    if load_to_staging and parsed_entries:
        loader = StagingLoader('ema_epar')
        stats = loader.load_records(
            parsed_entries,
            id_extractor=lambda r: r.get('epar_id') or r.get('medicine_name', '')[:100],
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        results['staging_stats'] = stats

    return results


if __name__ == "__main__":
    out = Path("data/raw/ema_epar")
    result = search_medicines(save_dir=out)
    print("Fetched EMA EPAR data")

