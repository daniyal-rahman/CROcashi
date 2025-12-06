from pathlib import Path
from typing import Any, Dict, List, Optional
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://portal.uspto.gov/pair/PublicPair"


def parse_patent_application(html_content: str, app_number: str) -> Optional[Dict[str, Any]]:
    """Parse patent application data from Public PAIR HTML."""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Extract title
        title = None
        title_elem = soup.find(["h1", "h2", "h3"]) or soup.find("div", class_=lambda x: x and "title" in x.lower())
        if title_elem:
            title = title_elem.get_text(strip=True)
        
        # Extract assignees
        assignees = []
        assignee_elems = soup.find_all(["div", "span"], class_=lambda x: x and "assignee" in x.lower())
        for elem in assignee_elems:
            assignee_text = elem.get_text(strip=True)
            if assignee_text:
                assignees.append(assignee_text)
        
        # Extract dates
        filing_date = None
        publication_date = None
        date_elems = soup.find_all(["div", "span"], class_=lambda x: x and "date" in x.lower())
        for elem in date_elems:
            date_text = elem.get_text(strip=True)
            # Try to parse dates
            date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', date_text)
            if date_match:
                if not filing_date:
                    filing_date = date_match.group(1)
                elif not publication_date:
                    publication_date = date_match.group(1)
        
        # Extract status
        status = None
        status_elem = soup.find(["div", "span"], class_=lambda x: x and "status" in x.lower())
        if status_elem:
            status = status_elem.get_text(strip=True)
        
        return {
            'application_number': app_number,
            'patent_number': app_number,  # May be same as application number
            'title': title,
            'assignees': assignees,
            'filing_date': filing_date,
            'publication_date': publication_date,
            'status': status,
            'raw_html': html_content[:50000] if len(html_content) > 50000 else html_content
        }
    except Exception as e:
        print(f"Error parsing patent application: {e}")
        return None


def search_application(
    app_number: str,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Search USPTO Public PAIR for patent application.
    
    Args:
        app_number: Patent application number
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table
    
    Note: Public PAIR requires form submission; this is a basic structure
    """
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(BASE_URL)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    parsed_data = None
    if app_number:
        # Try to parse if we have application number
        parsed_data = parse_patent_application(html, app_number)

    results: Dict[str, Any] = {
        "html": html,
        "forms_found": len(soup.find_all("form")),
        "parsed_data": parsed_data,
        "note": "Public PAIR requires form-based search; manual implementation needed",
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "uspto_public_pair.html", html)
        import json
        if parsed_data:
            write_text(Path(save_dir) / f"uspto_public_pair_{app_number}.json", json.dumps(parsed_data, indent=2, default=str))

    # Load to staging if requested and we have parsed data
    if load_to_staging and parsed_data:
        loader = StagingLoader('uspto_public_pair')
        stats = loader.load_records(
            [parsed_data],
            id_extractor=lambda r: r.get('application_number') or r.get('patent_number', ''),
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        results['staging_stats'] = stats

    return results


if __name__ == "__main__":
    out = Path("data/raw/uspto_public_pair")
    result = search_application("", save_dir=out)
    print("Fetched USPTO Public PAIR structure")

