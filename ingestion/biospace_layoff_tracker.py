from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.biospace.com/biospace-layoff-tracker"


def parse_layoff_entry(article_elem, base_url: str = BASE_URL) -> Optional[Dict[str, Any]]:
    """Parse individual layoff entry from article element."""
    try:
        title_elem = article_elem.find(["h1", "h2", "h3", "a"])
        if not title_elem:
            return None
        
        title = title_elem.get_text(strip=True)
        if not title or len(title) < 10:
            return None
        
        # Extract URL
        url = None
        link_elem = article_elem.find("a", href=True)
        if link_elem:
            href = link_elem.get("href", "")
            url = href if href.startswith("http") else f"{base_url.rstrip('/')}{href}"
        
        # Try to extract date
        date_elem = article_elem.find(["time", "span"], class_=lambda x: x and "date" in x.lower())
        layoff_date = None
        if date_elem:
            layoff_date = date_elem.get_text(strip=True)
        
        # Try to extract employee count
        text = article_elem.get_text()
        employees_affected = None
        employee_patterns = [
            r'(\d+)\s+employees?',
            r'layoff[:\s]+(\d+)',
            r'cut[:\s]+(\d+)',
        ]
        
        for pattern in employee_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    employees_affected = int(match.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        
        return {
            'title': title,
            'url': url,
            'layoff_date': layoff_date,
            'employees_affected': employees_affected,
            'raw_text': text[:5000] if len(text) > 5000 else text
        }
    except Exception as e:
        print(f"Error parsing layoff entry: {e}")
        return None


def fetch_layoff_tracker(
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch BioSpace layoff tracker.
    
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
        
        layoffs = []
        for article in soup.find_all(["article", "div"], class_=lambda x: x and ("article" in x.lower() or "entry" in x.lower() or "card" in x.lower())):
            entry = parse_layoff_entry(article, BASE_URL)
            if entry:
                layoffs.append(entry)
                if len(layoffs) >= limit:
                    break
        
        result = {
            "html_length": len(html),
            "layoffs_found": len(layoffs),
            "layoffs": layoffs,
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "biospace_layoff_tracker.html", html)
            import json
            write_text(Path(save_dir) / "biospace_layoff_tracker.json", json.dumps(result, indent=2, default=str))
        
        # Load to staging if requested
        if load_to_staging and layoffs:
            loader = StagingLoader('biospace_layoff_tracker')
            stats = loader.load_records(
                layoffs,
                id_extractor=lambda r: r.get('url') or r.get('title', '')[:100],
                skip_duplicates=True
            )
            print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
            result['staging_stats'] = stats
        
        return result
    except Exception as e:
        return {
            "layoffs_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/biospace_layoff_tracker")
    result = fetch_layoff_tracker(save_dir=out)
    print(f"Fetched {result.get('layoffs_found', 0)} layoff entries")

