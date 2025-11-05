from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://clinicaltrials.gov/api/v2/studies"


def fetch_studies_sample(
    query_term: str = "cancer",
    page_size: int = 50,
    save_dir: Optional[Path] = None,
    requests_per_second: float = 3.0,
) -> Dict[str, Any]:
    client = HttpClient(requests_per_second=requests_per_second)
    params: Dict[str, Any] = {
        "query.term": query_term,
        "pageSize": page_size,
        "countTotal": "true",
    }
    resp = client.get(API_BASE, params=params)
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        output = Path(save_dir) / "clinicaltrials_gov_sample.json"
        write_text(output, resp.text)

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/clinicaltrials_gov")
    result = fetch_studies_sample(save_dir=out)
    print(f"Fetched {len(result.get('studies', []))} studies (sample)")


