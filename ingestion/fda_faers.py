from datetime import date
from pathlib import Path
from typing import List, Optional

from ingestion.utils.files import ensure_dir, write_bytes
from ingestion.utils.http import HttpClient


BASE = "https://fis.fda.gov/content/Exports"


def _quarter_str(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"{d.year}Q{q}"


def _recent_quarters(count: int = 8) -> List[str]:
    quarters: List[str] = []
    today = date.today()
    year = today.year
    quarter = (today.month - 1) // 3 + 1
    for _ in range(count):
        quarters.append(f"{year}Q{quarter}")
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    return quarters


def try_download_recent(save_dir: Optional[Path] = None, attempts: int = 8) -> List[Path]:
    patterns = [
        "FAERS_ascii_{q}.zip",
        "FAERS_{q}.zip",
    ]
    out_dir = Path("data/raw/fda_faers") if save_dir is None else Path(save_dir)
    ensure_dir(out_dir)
    client = HttpClient(requests_per_second=0.5)
    saved: List[Path] = []
    for q in _recent_quarters(attempts):
        for p in patterns:
            url = f"{BASE}/" + p.format(q=q)
            try:
                resp = client.get(url)
                if resp.status_code == 200 and resp.content:
                    out_path = out_dir / url.split("/")[-1]
                    write_bytes(out_path, resp.content)
                    saved.append(out_path)
                    break
            except Exception:
                continue
    return saved


if __name__ == "__main__":
    files = try_download_recent()
    print(f"Downloaded {len(files)} FAERS files")


