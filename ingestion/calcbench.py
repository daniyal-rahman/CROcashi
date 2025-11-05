from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.calcbench.com/api"


def search_companies(query: str = "biotech", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search Calcbench for company financial data."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    # Note: Calcbench requires registration for API access
    # Try to access the API endpoint to see response structure
    try:
        resp = client.get(f"{API_BASE}/companies")
        data = client.json_or_text(resp)
        
        if isinstance(data, dict):
            if "error" in data or "message" in data:
                result = {
                    "note": "API access may require authentication",
                    "response": str(data)[:200],
                }
            else:
                result = {
                    "companies_count": len(data) if isinstance(data, list) else 0,
                    "data_keys": list(data.keys())[:5] if isinstance(data, dict) else [],
                }
        else:
            result = {
                "raw_response": str(data)[:200],
            }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            import json
            write_text(Path(save_dir) / "calcbench.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "error": str(e),
            "note": "Calcbench API may require authentication",
        }


if __name__ == "__main__":
    out = Path("data/raw/calcbench")
    result = search_companies(save_dir=out)
    print(f"Calcbench result: {result.get('note', result.get('companies_count', 'error'))}")

