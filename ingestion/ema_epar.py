from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.ema.europa.eu/en/medicines"


def search_medicines(query: str = "", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search EMA Product Database (EPAR)."""
    client = HttpClient(requests_per_second=1.0)
    # EMA may have JSON endpoints; using search for now
    resp = client.get(API_BASE, params={"search": query} if query else None)
    html = resp.text

    # Check if JSON response (EMA sometimes returns JSON)
    import json

    try:
        data = json.loads(html)
        is_json = True
    except:
        data = {"html": html[:1000]}
        is_json = False

    results: Dict[str, Any] = {
        "is_json": is_json,
        "data": data,
    }

    if save_dir is not None:
        ensure_dir(save_dir)
        if is_json:
            write_text(Path(save_dir) / "ema_epar_search.json", json.dumps(data, indent=2))
        else:
            write_text(Path(save_dir) / "ema_epar_search.html", html)

    return results


if __name__ == "__main__":
    out = Path("data/raw/ema_epar")
    result = search_medicines(save_dir=out)
    print("Fetched EMA EPAR data")

