"""Helper functions to verify data retrieval."""
from typing import Any, Dict


def verify_data_retrieved(result: Any, min_size: int = 100) -> Dict[str, Any]:
    """Verify that we actually retrieved data from a source."""
    verification = {
        "has_data": False,
        "data_type": type(result).__name__,
        "size": 0,
        "details": {},
    }
    
    if isinstance(result, dict):
        verification["size"] = len(result)
        verification["has_data"] = len(result) > 0 and "error" not in str(result).lower()
        verification["details"] = {
            "keys": list(result.keys())[:5],
            "has_error_key": "error" in result,
        }
    elif isinstance(result, list):
        verification["size"] = len(result)
        verification["has_data"] = len(result) > 0
        verification["details"] = {"first_item_type": type(result[0]).__name__ if result else None}
    elif isinstance(result, (str, bytes)):
        verification["size"] = len(result)
        verification["has_data"] = len(result) > min_size
    elif hasattr(result, "__len__"):
        verification["size"] = len(result)
        verification["has_data"] = len(result) > 0
    
    # Check for empty or error responses
    result_str = str(result).lower()
    if any(term in result_str for term in ["error", "not found", "no data", "empty", "null"]):
        verification["has_data"] = False
    
    return verification

