from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "http://export.arxiv.org/api/query"


def search(query: str = "cat:q-bio.*", max_results: int = 50, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search arXiv for q-bio category preprints."""
    client = HttpClient(requests_per_second=1.0)
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
    }
    resp = client.get(API_BASE, params=params)
    xml_text = resp.text

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "arxiv_search.xml", xml_text)

    # Return raw XML for now (can parse with xml.etree later)
    return {"xml": xml_text}


if __name__ == "__main__":
    out = Path("data/raw/arxiv")
    result = search(save_dir=out)
    print("Fetched arXiv q-bio preprints")

