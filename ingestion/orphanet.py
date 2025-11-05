from pathlib import Path
from typing import Any, Dict, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


API_BASE = "https://www.orphadata.com/data/xml"


def fetch_rare_diseases(save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Fetch Orphanet rare disease data."""
    client = HttpClient(requests_per_second=1.0)
    # Orphanet provides XML files for download
    resp = client.get(f"{API_BASE}/en_product1.xml")
    xml_text = resp.text

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "orphanet_rare_diseases.xml", xml_text)

    return {"xml_length": len(xml_text), "note": "XML file downloaded"}


if __name__ == "__main__":
    out = Path("data/raw/orphanet")
    result = fetch_rare_diseases(save_dir=out)
    print("Fetched Orphanet rare disease data")

