from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.accessdata.fda.gov/scripts/opdlisting/oopd/"


def parse_orphan_text(text: str) -> Dict[str, Any]:
    """Parse orphan designation text to extract structured data."""
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


def fetch_orphan_designations(
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Fetch FDA Orphan Drug designations.
    
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

    parsed_designations = []
    
    # Parse forms (search forms may contain data)
    forms = soup.find_all("form")
    for form in forms:
        form_text = form.get_text(strip=True)
        if form_text and len(form_text) > 20:
            parsed = parse_orphan_text(form_text)
            parsed['source'] = 'form'
            parsed_designations.append(parsed)
    
    # Parse tables
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                row_text = " ".join([cell.get_text(strip=True) for cell in cells])
                if row_text and len(row_text) > 10:
                    parsed = parse_orphan_text(row_text)
                    parsed['source'] = 'table'
                    parsed_designations.append(parsed)

    results: Dict[str, Any] = {
        "html": html,
        "forms_found": len(forms),
        "tables_found": len(tables),
        "parsed_designations": len(parsed_designations),
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "fda_orphan.html", html)
        import json
        if parsed_designations:
            write_text(Path(save_dir) / "fda_orphan_parsed.json", json.dumps(parsed_designations, indent=2))

    # Load to staging if requested
    if load_to_staging and parsed_designations:
        loader = StagingLoader('fda_orphan')
        
        def orphan_id_extractor(r):
            # Use URL if unique
            url = r.get('url', '')
            if url and len(url) > 50:
                return url
            
            # Fallback: hash drug + disease + company for uniqueness
            from src.utils.id_generation import generate_hash_id
            drug = r.get('drug_name', '')
            disease = r.get('disease_name', '')
            company = r.get('company_name', '')
            date = r.get('designation_date', '')
            if drug or disease or company:
                return generate_hash_id('FDA-ORPHAN', drug, disease, company, date)
            return r.get('raw_text', '')[:100] or ''
        
        stats = loader.load_records(
            parsed_designations,
            id_extractor=orphan_id_extractor,
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        results['staging_stats'] = stats

    return results


if __name__ == "__main__":
    out = Path("data/raw/fda_orphan")
    result = fetch_orphan_designations(save_dir=out)
    print("Fetched FDA Orphan Drug designations")

