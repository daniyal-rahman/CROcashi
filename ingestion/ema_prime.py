from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.ema.europa.eu/en/human-regulatory/research-development/prime-priority-medicines"


def parse_prime_text(text: str) -> Dict[str, Any]:
    """Parse PRIME designation text to extract structured data."""
    designation_data = {
        'raw_text': text,
        'company_name': None,
        'drug_name': None,
        'disease_name': None,
        'designation_date': None,
        'additional_info': None
    }
    
    # Try to extract date
    date_patterns = [
        r'(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'([A-Z][a-z]+ \d{1,2}, \d{4})',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            designation_data['designation_date'] = match.group(1)
            break
    
    # Try to identify company, drug, and disease names
    parts = re.split(r'[-–—:]', text, maxsplit=3)
    if len(parts) >= 2:
        designation_data['company_name'] = parts[0].strip()
        designation_data['drug_name'] = parts[1].strip() if len(parts) > 1 else None
        designation_data['disease_name'] = parts[2].strip() if len(parts) > 2 else None
        if len(parts) > 3:
            designation_data['additional_info'] = parts[3].strip()
    
    return designation_data


def fetch_prime_designations(
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch EMA PRIME designations.
    
    Args:
        limit: Maximum number of designations to fetch
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table
    """
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        parsed_designations = []
        
        # Find PRIME designation links or tables
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "prime" in text.lower() or "prime" in href.lower():
                parsed = parse_prime_text(text)
                parsed['url'] = href if href.startswith("http") else f"https://www.ema.europa.eu{href}"
                parsed_designations.append(parsed)
                if len(parsed_designations) >= limit:
                    break
        
        # Also check tables
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    row_text = " ".join([cell.get_text(strip=True) for cell in cells])
                    if "prime" in row_text.lower():
                        parsed = parse_prime_text(row_text)
                        parsed['source'] = 'table'
                        parsed_designations.append(parsed)
                        if len(parsed_designations) >= limit:
                            break
        
        result = {
            "html_length": len(html),
            "designations_found": len(parsed_designations),
            "designations": parsed_designations,
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "ema_prime.html", html)
            import json
            write_text(Path(save_dir) / "ema_prime.json", json.dumps(result, indent=2, default=str))
        
        # Load to staging if requested
        if load_to_staging and parsed_designations:
            loader = StagingLoader('ema_prime')
            stats = loader.load_records(
                parsed_designations,
                id_extractor=lambda r: r.get('url') or r.get('raw_text', '')[:100],
                skip_duplicates=True
            )
            print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
            result['staging_stats'] = stats
        
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

