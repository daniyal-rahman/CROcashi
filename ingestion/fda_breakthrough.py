from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.fda.gov/drugs/nda-and-bla-approvals/breakthrough-therapy"


def parse_breakthrough_text(text: str) -> Dict[str, Any]:
    """Parse breakthrough designation text to extract structured data."""
    designation_data = {
        'raw_text': text,
        'company_name': None,
        'drug_name': None,
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
    
    # Try to identify company and drug names
    parts = re.split(r'[-–—:]', text, maxsplit=2)
    if len(parts) >= 2:
        designation_data['company_name'] = parts[0].strip()
        designation_data['drug_name'] = parts[1].strip()
        if len(parts) > 2:
            designation_data['additional_info'] = parts[2].strip()
    
    return designation_data


def scrape_designations(
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Scrape FDA Breakthrough Therapy designations.
    
    Args:
        save_dir: Optional directory to save raw HTML/JSON
        load_to_staging: Whether to load parsed records to staging table
    
    Returns:
        Dictionary with fetch results and statistics
    """
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract tables or lists of designations
    tables = soup.find_all("table")
    links = [a.get("href", "") for a in soup.find_all("a", href=True) if "breakthrough" in a.get("href", "").lower()]
    
    parsed_designations = []
    
    # Parse table data
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                row_text = " ".join([cell.get_text(strip=True) for cell in cells])
                if "breakthrough" in row_text.lower() or any(cell.get_text(strip=True) for cell in cells):
                    parsed = parse_breakthrough_text(row_text)
                    parsed['source'] = 'table'
                    parsed_designations.append(parsed)
    
    # Parse links
    for link in links:
        link_text = soup.find("a", href=link)
        if link_text:
            text = link_text.get_text(strip=True)
            parsed = parse_breakthrough_text(text)
            parsed['url'] = link if link.startswith("http") else f"https://www.fda.gov{link}"
            parsed_designations.append(parsed)

    results: Dict[str, Any] = {
        "html": html,
        "tables_count": len(tables),
        "links": links[:20],
        "parsed_designations": len(parsed_designations),
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_breakthrough.html", html)
        import json
        if parsed_designations:
            write_text(Path(save_dir) / "fda_breakthrough_parsed.json", json.dumps(parsed_designations, indent=2))

    # Load to staging if requested
    if load_to_staging and parsed_designations:
        loader = StagingLoader('fda_breakthrough')
        stats = loader.load_records(
            parsed_designations,
            id_extractor=lambda r: r.get('url') or r.get('raw_text', '')[:100],
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        results['staging_stats'] = stats

    return results


if __name__ == "__main__":
    out = Path("data/raw/fda_breakthrough")
    result = scrape_designations(save_dir=out)
    print("Fetched FDA Breakthrough Therapy designations")

