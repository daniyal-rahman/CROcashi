from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.fda.gov/emergency-preparedness-and-response/mcm-legal-regulatory-and-policy-framework/emergency-use-authorization"


def parse_eua_text(text: str) -> Dict[str, Any]:
    """Parse EUA text to extract structured data."""
    eua_data = {
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
            eua_data['authorization_date'] = match.group(1)
            break
    
    # Try to identify company and product names
    parts = re.split(r'[-–—:]', text, maxsplit=2)
    if len(parts) >= 2:
        eua_data['company_name'] = parts[0].strip()
        eua_data['product_name'] = parts[1].strip()
        if len(parts) > 2:
            eua_data['additional_info'] = parts[2].strip()
    
    return eua_data


def fetch_recent_euas(
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch FDA Emergency Use Authorizations.
    
    Args:
        limit: Maximum number of EUAs to fetch
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table
    """
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        parsed_euas = []
        
        # Find EUA links
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "eua" in text.lower() or "eua" in href.lower() or "emergency use" in text.lower():
                parsed = parse_eua_text(text)
                parsed['url'] = href if href.startswith("http") else f"https://www.fda.gov{href}"
                parsed_euas.append(parsed)
                if len(parsed_euas) >= limit:
                    break
        
        result = {
            "html_length": len(html),
            "euas_found": len(parsed_euas),
            "euas": parsed_euas,
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "fda_eua.html", html)
            import json
            write_text(Path(save_dir) / "fda_eua.json", json.dumps(result, indent=2, default=str))
        
        # Load to staging if requested
        if load_to_staging and parsed_euas:
            loader = StagingLoader('fda_eua')
            
            def eua_id_extractor(r):
                # Use full URL if unique, otherwise hash title + text
                url = r.get('url', '')
                if url and url != BASE_URL and len(url) > len(BASE_URL) + 10:
                    return url  # Full unique URL
                # Fallback: hash of title/text for uniqueness
                from src.utils.id_generation import generate_hash_id
                title = r.get('raw_text', '') or r.get('product_name', '')
                return generate_hash_id('EUA', title, url) if title else url
            
            stats = loader.load_records(
                parsed_euas,
                id_extractor=eua_id_extractor,
                skip_duplicates=True
            )
            print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
            result['staging_stats'] = stats
        
        return result
    except Exception as e:
        return {
            "euas_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/fda_eua")
    result = fetch_recent_euas(save_dir=out)
    print(f"Fetched {result.get('euas_found', 0)} EUAs")

