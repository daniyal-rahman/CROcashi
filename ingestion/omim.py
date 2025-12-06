from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://api.omim.org/api"


def search_entries(query: str = "cancer", limit: int = 10, api_key: Optional[str] = None, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search OMIM (Online Mendelian Inheritance in Man) database."""
    # Note: OMIM requires API key for full access
    # Try to get recent entries or search
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    # Try different endpoints
    endpoints_to_try = [
        f"{API_BASE}/entry/search",
        f"{API_BASE}/entry/list",
    ]
    
    result_data = None
    for endpoint in endpoints_to_try:
        params = {"format": "json", "limit": limit}
        if api_key:
            params["apiKey"] = api_key
        if endpoint.endswith("search"):
            params["search"] = query
        
        try:
            resp = client.get(endpoint, params=params)
            if resp.status_code == 200:
                data = client.json_or_text(resp)
                # Verify we got actual data
                if isinstance(data, dict) and len(data) > 0:
                    result_data = data
                    break
                elif isinstance(data, str) and len(data) > 100:
                    result_data = {"raw": data[:500], "note": "Got text response"}
                    break
        except Exception:
            continue
    
    if result_data is None:
        result_data = {"error": "No data retrieved", "note": "OMIM may require API key"}
    
    if save_dir is not None:
        ensure_dir(save_dir)
        import json
        write_text(Path(save_dir) / "omim_search.json", json.dumps(result_data, indent=2))
    
    return result_data


if __name__ == "__main__":
    out = Path("data/raw/omim")
    result = search_entries(save_dir=out)
    print("Fetched OMIM data")

