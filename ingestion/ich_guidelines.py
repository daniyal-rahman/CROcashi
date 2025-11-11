from pathlib import Path
from typing import Any, Dict, Optional, List

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


BASE_URL = "https://www.ich.org/page/ich-guidelines"


def fetch_guidelines(
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """Fetch ICH Guidelines."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        guidelines = []
        records = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a.get("href", "")
            if any(term in text.lower() for term in ["guideline", "q", "s", "e", "m"]):
                full_url = href if href.startswith("http") else f"https://www.ich.org{href}"
                guidelines.append({
                    "text": text[:150],
                    "href": full_url,
                })
                records.append({
                    'text': text[:200],
                    'title': text[:200],
                    'url': full_url,
                    'raw_text': text
                })
        
        result = {
            "html_length": len(html),
            "guidelines_found": len(guidelines),
            "guidelines": guidelines[:30],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "ich_guidelines.html", html)
            import json
            write_text(Path(save_dir) / "ich_guidelines.json", json.dumps(result, indent=2))
        
        stats = {'parsed': len(records), 'inserted': 0, 'skipped': 0, 'errors': 0}
        
        if load_to_staging and records:
            loader = StagingLoader('ich_guidelines')
            staging_stats = loader.load_records(
                records,
                id_extractor=lambda r: r.get('url') or r.get('text', '')[:100] or '',
                skip_duplicates=True
            )
            stats.update(staging_stats)
            print(f"Staging: {staging_stats['inserted']} inserted, {staging_stats['skipped']} skipped, {staging_stats['errors']} errors")
        
        result.update(stats)
        return result
    except Exception as e:
        return {
            "guidelines_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/ich_guidelines")
    result = fetch_guidelines(save_dir=out)
    print(f"Fetched {result.get('guidelines_found', 0)} ICH guidelines")

