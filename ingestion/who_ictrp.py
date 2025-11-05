from pathlib import Path
from typing import Optional

from ingestion.utils.files import ensure_dir, write_bytes
from ingestion.utils.http import HttpClient


def download_bulk_csv(
    download_url: str,
    save_dir: Optional[Path] = None,
    requests_per_second: float = 1.0,
) -> Path:
    client = HttpClient(requests_per_second=requests_per_second)
    resp = client.get(download_url)
    filename = download_url.split("/")[-1] or "ictrp.csv"
    out_dir = Path("data/raw/who_ictrp") if save_dir is None else Path(save_dir)
    ensure_dir(out_dir)
    out_path = out_dir / filename
    write_bytes(out_path, resp.content)
    return out_path


if __name__ == "__main__":
    # Provide the actual WHO ICTRP bulk CSV URL here when known
    # Example placeholder (must be replaced with the current official link):
    url = "https://trialsearch.who.int/Export/WHO-ICTRP-Results.csv"
    try:
        path = download_bulk_csv(url)
        print(f"Downloaded WHO ICTRP to {path}")
    except Exception as e:
        print(f"WHO ICTRP download failed: {e}")


