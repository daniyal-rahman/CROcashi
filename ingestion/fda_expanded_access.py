from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.fda.gov/news-events/public-health-focus/expanded-access-compassionate-use"


def parse_expanded_access_text(text: str) -> Dict[str, Any]:
    """Parse expanded access text to extract structured data."""
    access_data = {
        'raw_text': text,
        'company_name': None,
        'product_name': None,
        'authorization_date': None,
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
            access_data['authorization_date'] = match.group(1)
            break
    
    # Try to identify company and product names
    parts = re.split(r'[-–—:]', text, maxsplit=2)
    if len(parts) >= 2:
        access_data['company_name'] = parts[0].strip()
        access_data['product_name'] = parts[1].strip()
        if len(parts) > 2:
            access_data['additional_info'] = parts[2].strip()
    
    return access_data


def fetch_expanded_access(
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch FDA Expanded Access (Compassionate Use) information.
    
    Args:
        limit: Maximum number of entries to fetch
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table
    """
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        parsed_entries = []
        
        # Find expanded access links
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if any(term in text.lower() for term in ["expanded access", "compassionate", "eind", "e-ind"]):
                parsed = parse_expanded_access_text(text)
                parsed['url'] = href if href.startswith("http") else f"https://www.fda.gov{href}"
                parsed_entries.append(parsed)
                if len(parsed_entries) >= limit:
                    break
        
        result = {
            "html_length": len(html),
            "links_found": len(parsed_entries),
            "entries": parsed_entries,
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "fda_expanded_access.html", html)
            import json
            write_text(Path(save_dir) / "fda_expanded_access.json", json.dumps(result, indent=2, default=str))
        
        # Load to staging if requested
        if load_to_staging and parsed_entries:
            loader = StagingLoader('fda_expanded_access')
            
            def expanded_access_id_extractor(r):
                # Use full URL if unique
                url = r.get('url', '')
                if url and url != BASE_URL and len(url) > len(BASE_URL) + 10:
                    return url
                
                # Fallback: hash product + company for uniqueness
                from src.utils.id_generation import generate_hash_id
                product = r.get('product_name', '')
                company = r.get('company_name', '')
                date = r.get('authorization_date', '')
                if product or company:
                    return generate_hash_id('EXP-ACCESS', product, company, date)
                return url or r.get('raw_text', '')[:100] or ''
            
            stats = loader.load_records(
                parsed_entries,
                id_extractor=expanded_access_id_extractor,
                skip_duplicates=True
            )
            print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
            result['staging_stats'] = stats
        
        return result
    except Exception as e:
        return {
            "links_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/fda_expanded_access")
    result = fetch_expanded_access(save_dir=out)
    print(f"Fetched {result.get('links_found', 0)} expanded access links")

