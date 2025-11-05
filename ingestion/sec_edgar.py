from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://data.sec.gov/api/xbrl/companyconcept"


def get_company_concept(cik: str, taxonomy: str = "us-gaap", tag: str = "", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Get SEC EDGAR company concept data."""
    client = HttpClient(requests_per_second=1.0, user_agent="CROcashi-Ingestion contact@example.com")
    url = f"{API_BASE}/CIK{cik.zfill(10)}/{taxonomy}/{tag}.json" if tag else f"{API_BASE}/CIK{cik.zfill(10)}/{taxonomy}.json"
    resp = client.get(url)
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / f"sec_edgar_cik_{cik}.json", resp.text)

    return data  # type: ignore[return-value]


def search_company(name: str, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search for a company in SEC EDGAR (via companytickers endpoint)."""
    client = HttpClient(requests_per_second=1.0, user_agent="CROcashi-Ingestion contact@example.com")
    resp = client.get("https://www.sec.gov/files/company_tickers.json")
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "sec_company_tickers.json", resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/sec_edgar")
    tickers = search_company("", save_dir=out)
    print("Fetched SEC EDGAR company tickers")

