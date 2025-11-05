from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.alphavantage.co/query"


def get_stock_data(symbol: str = "MRNA", api_key: Optional[str] = None, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Get stock data from Alpha Vantage API."""
    client = HttpClient(requests_per_second=5.0, timeout_seconds=15.0)
    
    # Note: API key required for production use
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "compact",
    }
    if api_key:
        params["apikey"] = api_key
    else:
        # Without API key, we'll get a rate limit message but can verify endpoint works
        params["apikey"] = "demo"
    
    try:
        resp = client.get(API_BASE, params=params)
        data = client.json_or_text(resp)
        
        if isinstance(data, dict):
            if "Note" in data or "Error Message" in data:
                result = {
                    "note": "API key required or rate limited",
                    "response_keys": list(data.keys()),
                }
            else:
                result = {
                    "symbol": symbol,
                    "data_keys": list(data.keys())[:5],
                    "has_data": len(data) > 0,
                }
        else:
            result = {
                "raw_response": str(data)[:200],
            }
        
        if save_dir is not None:
            ensure_dir(save_dir)
            import json
            write_text(Path(save_dir) / "alphavantage.json", json.dumps(result, indent=2))
        
        return result
    except Exception as e:
        return {
            "error": str(e),
        }


if __name__ == "__main__":
    out = Path("data/raw/alphavantage")
    result = get_stock_data(save_dir=out)
    print(f"Alpha Vantage result: {result.get('note', result.get('has_data', 'error'))}")

