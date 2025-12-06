from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.fda.gov/drugs/drug-safety-and-availability/clinical-holds-list"


def parse_clinical_hold_text(text: str) -> Dict[str, Any]:
    """
    Parse clinical hold text to extract structured data.
    
    Typical format: "Company Name - Drug Name - Date - Additional Info"
    """
    hold_data = {
        'raw_text': text,
        'company_name': None,
        'drug_name': None,
        'hold_date': None,
        'hold_type': None,
        'additional_info': None
    }
    
    # Try to extract date (various formats)
    date_patterns = [
        r'(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'([A-Z][a-z]+ \d{1,2}, \d{4})',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            hold_data['hold_date'] = match.group(1)
            break
    
    # Try to identify company and drug names
    # Common patterns: "Company - Drug", "Company: Drug", etc.
    parts = re.split(r'[-–—:]', text, maxsplit=2)
    if len(parts) >= 2:
        hold_data['company_name'] = parts[0].strip()
        hold_data['drug_name'] = parts[1].strip()
        if len(parts) > 2:
            hold_data['additional_info'] = parts[2].strip()
    
    # Try to identify hold type
    text_lower = text.lower()
    if 'full' in text_lower and 'hold' in text_lower:
        hold_data['hold_type'] = 'full'
    elif 'partial' in text_lower:
        hold_data['hold_type'] = 'partial'
    else:
        hold_data['hold_type'] = 'unknown'
    
    return hold_data


def fetch_clinical_holds(
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch FDA Clinical Hold Database.
    
    Args:
        save_dir: Optional directory to save raw HTML/JSON
        load_to_staging: Whether to load parsed records to staging table
    
    Returns:
        Dictionary with fetch results and statistics
    """
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        holds = []
        parsed_holds = []
        
        # Look for links and text that mention clinical holds
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if "clinical hold" in text.lower() or "hold" in href.lower():
                hold_info = {
                    "text": text[:200],
                    "href": href if href.startswith("http") else f"https://www.fda.gov{href}",
                }
                holds.append(hold_info)
                
                # Parse structured data
                parsed = parse_clinical_hold_text(text)
                parsed['url'] = hold_info['href']
                parsed_holds.append(parsed)
        
        # Also look for tables or structured lists
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) >= 2:
                    row_text = " ".join([cell.get_text(strip=True) for cell in cells])
                    if "clinical hold" in row_text.lower() or "hold" in row_text.lower():
                        parsed = parse_clinical_hold_text(row_text)
                        parsed['source'] = 'table'
                        parsed_holds.append(parsed)
        
        result = {
            "html_length": len(html),
            "holds_found": len(holds),
            "parsed_holds": len(parsed_holds),
            "holds": holds[:20],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "fda_clinical_hold.html", html)
            import json
            write_text(Path(save_dir) / "fda_clinical_hold.json", json.dumps(result, indent=2))
            if parsed_holds:
                write_text(Path(save_dir) / "fda_clinical_hold_parsed.json", json.dumps(parsed_holds, indent=2))
        
        # Load to staging if requested
        if load_to_staging and parsed_holds:
            loader = StagingLoader('fda_clinical_hold')
            stats = loader.load_records(
                parsed_holds,
                id_extractor=lambda r: r.get('url') or r.get('raw_text', '')[:100],
                skip_duplicates=True
            )
            print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
            result['staging_stats'] = stats
        
        return result
    except Exception as e:
        return {
            "holds_found": 0,
            "parsed_holds": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/fda_clinical_hold")
    result = fetch_clinical_holds(save_dir=out)
    print(f"Fetched {result.get('holds_found', 0)} clinical holds")

