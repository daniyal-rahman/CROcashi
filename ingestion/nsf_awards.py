from pathlib import Path
from typing import Any, Dict, Optional, List

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader


API_BASE = "https://api.nsf.gov/services/v1/awards.json"


def search_awards(
    query: str = "biotech",
    limit: int = 50,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True
) -> Dict[str, Any]:
    """Search NSF awards."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    params = {
        "keyword": query,
        "limit": limit,
    }
    
    try:
        resp = client.get(API_BASE, params=params)
        data = client.json_or_text(resp)
        
        # Extract awards from response
        awards_list = []
        if isinstance(data, dict):
            awards_list = data.get("response", {}).get("award", [])
        elif isinstance(data, list):
            awards_list = data
        
        records = []
        for award in awards_list:
            if isinstance(award, dict):
                records.append({
                    'award_id': award.get('id', ''),
                    'award_number': award.get('awardNumber', ''),
                    'organization_name': award.get('organization', {}).get('name', '') if isinstance(award.get('organization'), dict) else '',
                    'institution': award.get('organization', {}).get('name', '') if isinstance(award.get('organization'), dict) else '',
                    'title': award.get('title', ''),
                    'raw_data': award
                })
        
        result = {
            "awards_count": len(awards_list),
            "awards": awards_list[:10] if awards_list else [],
        }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            import json
            write_text(Path(save_dir) / "nsf_awards.json", json.dumps(result, indent=2))
        
        stats = {'parsed': len(records), 'inserted': 0, 'skipped': 0, 'errors': 0}
        
        if load_to_staging and records:
            loader = StagingLoader('nsf_awards')
            staging_stats = loader.load_records(
                records,
                id_extractor=lambda r: r.get('award_id') or r.get('award_number') or '',
                skip_duplicates=True
            )
            stats.update(staging_stats)
            print(f"Staging: {staging_stats['inserted']} inserted, {staging_stats['skipped']} skipped, {staging_stats['errors']} errors")
        
        result.update(stats)
        return result
    except Exception as e:
        return {
            "awards_count": 0,
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/nsf_awards")
    result = search_awards(save_dir=out)
    print(f"Fetched {result.get('awards_count', 0)} NSF awards")

