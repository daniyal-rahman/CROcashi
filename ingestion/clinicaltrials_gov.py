from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader, clinicaltrials_id_extractor


API_BASE = "https://clinicaltrials.gov/api/v2/studies"


def fetch_studies_sample(
    query_term: str = "cancer",
    page_size: int = 50,
    save_dir: Optional[Path] = None,
    requests_per_second: float = 3.0,
    load_to_staging: bool = True,
) -> Dict[str, Any]:
    """
    Fetch clinical trials from ClinicalTrials.gov.
    
    Args:
        query_term: Search query
        page_size: Number of results to fetch
        save_dir: Optional directory to save raw JSON
        requests_per_second: Rate limit
        load_to_staging: Whether to load data into staging table (default: True)
        
    Returns:
        Dict with fetched data
    """
    client = HttpClient(requests_per_second=requests_per_second)
    params: Dict[str, Any] = {
        "query.term": query_term,
        "pageSize": page_size,
        "countTotal": "true",
    }
    resp = client.get(API_BASE, params=params)
    data = client.json_or_text(resp)

    # Save to file if requested
    if save_dir is not None:
        ensure_dir(save_dir)
        output = Path(save_dir) / "clinicaltrials_gov_sample.json"
        write_text(output, resp.text)

    # Load to staging table for processing
    if load_to_staging and isinstance(data, dict) and 'studies' in data:
        loader = StagingLoader('clinicaltrials_gov')
        stats = loader.load_records(
            data['studies'],
            id_extractor=clinicaltrials_id_extractor,
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/clinicaltrials_gov")
    result = fetch_studies_sample(save_dir=out, load_to_staging=True)
    print(f"Fetched {len(result.get('studies', []))} studies (sample)")


