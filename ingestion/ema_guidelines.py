from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.ema.europa.eu/en/human-regulatory/research-development/scientific-guidelines"


def parse_guideline_entry(link_elem, base_url: str = BASE_URL) -> Optional[Dict[str, Any]]:
    """Parse individual guideline entry from link element."""
    try:
        text = link_elem.get_text(strip=True)
        href = link_elem.get("href", "")
        
        if not text or len(text) < 5:
            return None
        
        # Try to extract publication date
        publication_date = None
        date_patterns = [
            r'(\d{1,2}/\d{1,2}/\d{4})',
            r'(\d{4}-\d{2}-\d{2})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                publication_date = match.group(1)
                break
        
        return {
            'title': text,
            'url': href if href.startswith("http") else f"https://www.ema.europa.eu{href}",
            'publication_date': publication_date,
            'raw_text': text
        }
    except Exception as e:
        print(f"Error parsing guideline entry: {e}")
        return None


def fetch_guidelines(
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch EMA Guidelines.
    
    Args:
        limit: Maximum number of guidelines to fetch
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table
    """
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        parsed_guidelines = []
        
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "guideline" in text.lower() or "guideline" in href.lower():
                entry = parse_guideline_entry(a, BASE_URL)
                if entry:
                    parsed_guidelines.append(entry)
                    if len(parsed_guidelines) >= limit:
                        break
        
        result = {
            "html_length": len(html),
            "guidelines_found": len(parsed_guidelines),
            "guidelines": parsed_guidelines,
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "ema_guidelines.html", html)
            import json
            write_text(Path(save_dir) / "ema_guidelines.json", json.dumps(result, indent=2, default=str))
        
        # Load to staging if requested
        if load_to_staging and parsed_guidelines:
            loader = StagingLoader('ema_guidelines')
            stats = loader.load_records(
                parsed_guidelines,
                id_extractor=lambda r: r.get('url') or r.get('title', '')[:100],
                skip_duplicates=True
            )
            print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
            result['staging_stats'] = stats
        
        return result
    except Exception as e:
        return {
            "guidelines_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/ema_guidelines")
    result = fetch_guidelines(save_dir=out)
    print(f"Fetched {result.get('guidelines_found', 0)} EMA guidelines")

