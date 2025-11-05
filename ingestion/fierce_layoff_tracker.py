from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


BASE_URL = "https://www.fiercebiotech.com/special-reports/fierce-biotech-layoff-tracker"


def fetch_layoff_tracker(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch FierceBiotech layoff tracker."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    try:
        resp = client.get(BASE_URL)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        
        # Find layoff entries
        layoffs = []
        for article in soup.find_all(["article", "div"], class_=lambda x: x and ("article" in x.lower() or "entry" in x.lower())):
            title_elem = article.find(["h1", "h2", "h3", "a"])
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title and len(title) > 10:
                    layoffs.append({
                        "title": title[:150],
                    })
        
        result = {
            "html_length": len(html),
            "layoffs_found": len(layoffs),
            "layoffs": layoffs[:30],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            write_text(Path(save_dir) / "fierce_layoff_tracker.html", html)
            import json
            write_text(Path(save_dir) / "fierce_layoff_tracker.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "layoffs_found": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/fierce_layoff_tracker")
    result = fetch_layoff_tracker(save_dir=out)
    print(f"Fetched {result.get('layoffs_found', 0)} layoff entries")

