from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader, patentsview_id_extractor


API_BASE = "https://api.patentsview.org/patents/query"


def search_patents(
    query: str = '{"_gte":{"patent_date":"2020-01-01"}}',
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """
    Search USPTO PatentsView API.
    
    Args:
        query: JSON query string for PatentsView API
        limit: Number of results to fetch
        save_dir: Optional directory to save raw JSON
        load_to_staging: Whether to load data into staging table (default: True)
        
    Returns:
        Dict with fetched data
    """
    client = HttpClient(requests_per_second=2.0)
    params = {
        "q": query,
        "f": '["patent_number","patent_date","assignee_organization","title"]',
        "o": {"per_page": limit, "page": 1},
    }
    resp = client.session.post(API_BASE, json=params, headers={"Content-Type": "application/json", **client.default_headers}, timeout=client.timeout_seconds)
    data = client.json_or_text(resp)

    # Save to file if requested
    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "patentsview_search.json", resp.text)

    # Load to staging table for processing
    if load_to_staging and isinstance(data, dict) and 'patents' in data:
        loader = StagingLoader('patentsview')
        stats = loader.load_records(
            data['patents'],
            id_extractor=patentsview_id_extractor,
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")

    return data  # type: ignore[return-value]


if __name__ == "__main__":
    out = Path("data/raw/patentsview")
    result = search_patents(save_dir=out)
    print("Fetched PatentsView data")

