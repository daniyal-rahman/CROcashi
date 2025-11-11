from pathlib import Path
from typing import Dict, List, Optional, Any
import re

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


SEARCH_URL = "https://www.clinicaltrialsregister.eu/ctr-search/search"


def parse_trial_row(row_elem) -> Optional[Dict[str, Any]]:
    """Parse individual trial row from table."""
    try:
        cols = [c.get_text(strip=True) for c in row_elem.find_all(["td", "th"])]
        if len(cols) < 2:
            return None
        
        # Try to extract EudraCT number (usually in first column)
        eudract_number = None
        for col in cols:
            if re.match(r'EudraCT\s+No:\s*\d{4}-\d{6}-\d{2}', col, re.IGNORECASE):
                eudract_match = re.search(r'(\d{4}-\d{6}-\d{2})', col)
                if eudract_match:
                    eudract_number = eudract_match.group(1)
                    break
        
        return {
            'eudract_number': eudract_number,
            'trial_title': cols[0] if len(cols) > 0 else '',
            'sponsor': cols[1] if len(cols) > 1 else '',
            'raw_data': ' | '.join(cols)
        }
    except Exception as e:
        print(f"Error parsing trial row: {e}")
        return None


def scrape_search_first_page(
    query: str = "cancer",
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Scrape EMA Clinical Trials Register search results.
    
    Args:
        query: Search query
        limit: Maximum number of trials to fetch
        save_dir: Optional directory to save raw HTML
        load_to_staging: Whether to load data into staging table
    """
    client = HttpClient(requests_per_second=0.5)
    resp = client.get(SEARCH_URL, params={"query": query})
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    parsed_trials = []
    table = soup.find("table", {"class": "result"})
    if table:
        for tr in table.find_all("tr"):
            trial_data = parse_trial_row(tr)
            if trial_data:
                parsed_trials.append(trial_data)
                if len(parsed_trials) >= limit:
                    break

    result = {
        "html_length": len(html),
        "trials_found": len(parsed_trials),
        "trials": parsed_trials,
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "ema_search_first_page.html", html)
        import json
        write_text(Path(save_dir) / "ema_trials.json", json.dumps(result, indent=2, default=str))

    # Load to staging if requested
    if load_to_staging and parsed_trials:
        loader = StagingLoader('ema_trials')
        stats = loader.load_records(
            parsed_trials,
            id_extractor=lambda r: r.get('eudract_number') or r.get('trial_title', '')[:100],
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
        result['staging_stats'] = stats

    return result


if __name__ == "__main__":
    out = Path("data/raw/ema_trials")
    results = scrape_search_first_page(save_dir=out)
    print(f"Parsed {len(results)} rows from EMA trials search page")


