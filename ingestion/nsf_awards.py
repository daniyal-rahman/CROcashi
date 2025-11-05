from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://api.nsf.gov/services/v1/awards.json"


def search_awards(query: str = "biotech", limit: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search NSF awards."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    params = {
        "keyword": query,
        "limit": limit,
    }
    
    try:
        resp = client.get(API_BASE, params=params)
        data = client.json_or_text(resp)
        
        # Verify we got actual data
        if isinstance(data, dict):
            awards = data.get("response", {}).get("award", [])
            result = {
                "awards_count": len(awards),
                "awards": awards[:10] if awards else [],
            }
        elif isinstance(data, list):
            result = {
                "awards_count": len(data),
                "awards": data[:10],
            }
        else:
            result = {
                "raw_data": str(data)[:500],
                "awards_count": 0,
            }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            import json
            write_text(Path(save_dir) / "nsf_awards.json", json.dumps(result, indent=2))
        
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

