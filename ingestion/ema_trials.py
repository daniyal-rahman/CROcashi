from pathlib import Path
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


SEARCH_URL = "https://www.clinicaltrialsregister.eu/ctr-search/search"


def scrape_search_first_page(query: str = "cancer", save_dir: Optional[Path] = None) -> List[Dict[str, str]]:
    client = HttpClient(requests_per_second=0.5)
    resp = client.get(SEARCH_URL, params={"query": query})
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    rows: List[Dict[str, str]] = []
    table = soup.find("table", {"class": "result"})
    if table:
        for tr in table.find_all("tr"):
            cols = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if len(cols) >= 2:
                rows.append({"col_0": cols[0], "col_1": cols[1] if len(cols) > 1 else ""})

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "ema_search_first_page.html", html)

    return rows


if __name__ == "__main__":
    out = Path("data/raw/ema_trials")
    results = scrape_search_first_page(save_dir=out)
    print(f"Parsed {len(results)} rows from EMA trials search page")


