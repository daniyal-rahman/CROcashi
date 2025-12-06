from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.utils.files import ensure_dir, write_bytes
from ingestion.utils.http import HttpClient


BASE_URL = "https://vaers.hhs.gov/data/datasets.html"


def download_recent_years(years: List[int] = None, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Download VAERS data files for recent years."""
    from bs4 import BeautifulSoup
    
    if years is None:
        from datetime import date
        current_year = date.today().year
        years = [current_year - 1, current_year]  # Last 2 years
    
    out_dir = Path("data/raw/vaers") if save_dir is None else Path(save_dir)
    ensure_dir(out_dir)
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    saved: List[Path] = []
    
    # First, get the data download page to find actual file links
    try:
        resp = client.get(BASE_URL)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Find all download links - VAERS uses /eSubDownload/index.jsp?fn= format
        links = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if any(ext in href.lower() for ext in [".csv", ".zip", ".xlsx"]) or "vasubdownload" in href.lower():
                if href.startswith("http"):
                    links.append(href)
                elif href.startswith("/"):
                    links.append(f"https://vaers.hhs.gov{href}")
                else:
                    links.append(f"https://vaers.hhs.gov/eSubDownload/{href}")
        
        # Download files for recent years - try to get current year's data
        for year in years:
            for link in links:
                if str(year) in link or "AllVAERS" in link.upper():
                    try:
                        file_resp = client.get(link)
                        if file_resp.status_code == 200 and len(file_resp.content) > 10000:  # Valid file > 10KB
                            # Extract filename from URL or use default
                            if "fn=" in link:
                                filename = link.split("fn=")[-1].split("&")[0]
                            else:
                                filename = link.split("/")[-1] or f"vaers_{year}.csv"
                            out_path = out_dir / filename
                            write_bytes(out_path, file_resp.content)
                            saved.append(out_path)
                            break  # Found file for this year
                    except Exception:
                        continue
    except Exception as e:
        return {
            "files_downloaded": 0,
            "files": [],
            "file_sizes": [],
            "error": str(e),
        }
    
    return {
        "files_downloaded": len(saved),
        "files": [str(f) for f in saved],
        "file_sizes": [f.stat().st_size if f.exists() else 0 for f in saved],
    }


if __name__ == "__main__":
    files = download_recent_years()
    print(f"Downloaded {len(files)} VAERS files")

