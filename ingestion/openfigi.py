from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://api.openfigi.com/v3"


def search_figis(query: str = "MRNA", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search OpenFIGI for financial instrument identifiers."""
    client = HttpClient(requests_per_second=1.0, timeout_seconds=15.0)
    
    # OpenFIGI uses POST requests
    payload = [{"idType": "TICKER", "idValue": query}]
    
    try:
        resp = client.get(f"{API_BASE}/search", json=payload)
        data = client.json_or_text(resp)
        
        if isinstance(data, list) and len(data) > 0:
            result = {
                "figis_found": len(data),
                "figis": data[:5],
            }
        elif isinstance(data, dict):
            result = {
                "response": data,
            }
        else:
            result = {
                "raw_response": str(data)[:200],
            }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            import json
            write_text(Path(save_dir) / "openfigi.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        # Try GET as fallback
        try:
            resp = client.get(f"{API_BASE}/search", params={"ticker": query})
            data = client.json_or_text(resp)
            return {
                "figis_found": len(data) if isinstance(data, list) else 0,
                "response": data,
            }
        except:
            return {
                "error": str(e),
            }


if __name__ == "__main__":
    out = Path("data/raw/openfigi")
    result = search_figis(save_dir=out)
    print(f"OpenFIGI result: {result.get('figis_found', 0)} FIGIs found")

