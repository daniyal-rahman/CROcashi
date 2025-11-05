from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup

from ingestion.utils.files import ensure_dir, write_bytes
from ingestion.utils.http import HttpClient


PAGE_URL = "https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files"


def list_orange_book_links(page_url: str = PAGE_URL) -> List[str]:
    client = HttpClient(requests_per_second=1.0)
    resp = client.get(page_url)
    soup = BeautifulSoup(resp.text, "html.parser")
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/media/") or href.startswith("https://www.fda.gov/media/"):
            if any(href.lower().endswith(ext) for ext in (".zip", ".csv", ".xlsx")):
                if href.startswith("/media/"):
                    href = f"https://www.fda.gov{href}"
                links.append(href)
    return links


def download_all(save_dir: Optional[Path] = None) -> List[Path]:
    links = list_orange_book_links()
    out_dir = Path("data/raw/fda_orange_book") if save_dir is None else Path(save_dir)
    ensure_dir(out_dir)
    client = HttpClient(requests_per_second=1.0)
    saved: List[Path] = []
    for url in links:
        filename = url.rstrip("/").split("/")[-1]
        out_path = out_dir / filename
        resp = client.get(url)
        write_bytes(out_path, resp.content)
        saved.append(out_path)
    return saved


if __name__ == "__main__":
    paths = download_all()
    print(f"Downloaded {len(paths)} Orange Book files")


