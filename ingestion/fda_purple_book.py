from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


SEARCH_URL = "https://purplebooksearch.fda.gov/"


def parse_biosimilar_entry(entry_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse individual biosimilar entry to extract structured data."""
    parsed = {
        'biosimilar_id': entry_data.get('biosimilar_id') or entry_data.get('id', ''),
        'product_name': entry_data.get('product_name') or entry_data.get('name', ''),
        'sponsor_name': entry_data.get('sponsor_name') or entry_data.get('applicant', ''),
        'reference_product': entry_data.get('reference_product') or entry_data.get('reference', ''),
        'approval_date': entry_data.get('approval_date') or entry_data.get('date', ''),
    }
    return parsed


def search_biosimilars(
    query: str = "",
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Search FDA Purple Book for biosimilars.
    
    Args:
        query: Search query
        limit: Maximum number of results
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table
    """
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(SEARCH_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    parsed_entries = []
    
    # Look for biosimilar entries in HTML
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        href = link.get("href", "")
        if "biosimilar" in text.lower() or "biosimilar" in href.lower():
            if text and len(text) > 5:
                parsed = {
                    'product_name': text,
                    'url': href if href.startswith("http") else f"https://purplebooksearch.fda.gov{href}",
                }
                parsed_entries.append(parsed)
                if len(parsed_entries) >= limit:
                    break
    
    # Also check tables
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                row_data = {}
                for i, cell in enumerate(cells):
                    text = cell.get_text(strip=True)
                    if i == 0:
                        row_data['product_name'] = text
                    elif i == 1:
                        row_data['sponsor_name'] = text
                    elif i == 2:
                        row_data['approval_date'] = text
                
                if row_data.get('product_name'):
                    parsed = parse_biosimilar_entry(row_data)
                    parsed_entries.append(parsed)
                    if len(parsed_entries) >= limit:
                        break

    results: Dict[str, Any] = {
        "html_length": len(html),
        "forms_found": len(soup.find_all("form")),
        "biosimilars_found": len(parsed_entries),
        "entries": parsed_entries,
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_purple_book.html", html)
        import json
        if parsed_entries:
            write_text(Path(save_dir) / "fda_purple_book.json", json.dumps(results, indent=2, default=str))

    # Load to staging if requested
    if load_to_staging and parsed_entries:
        loader = StagingLoader('fda_purple_book')
        stats = loader.load_records(
            parsed_entries,
            id_extractor=lambda r: r.get('biosimilar_id') or r.get('product_name', '')[:100],
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        results['staging_stats'] = stats

    return results


if __name__ == "__main__":
    out = Path("data/raw/fda_purple_book")
    result = search_biosimilars(save_dir=out)
    print("Fetched FDA Purple Book data")

