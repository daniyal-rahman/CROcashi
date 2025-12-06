from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def esearch(term: str, retmax: int = 50, api_key: Optional[str] = None) -> Dict[str, Any]:
    client = HttpClient(requests_per_second=10.0 if api_key else 3.0)
    params = {
        "db": "pmc",
        "term": term,
        "retmax": retmax,
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key
    resp = client.get(f"{EUTILS_BASE}/esearch.fcgi", params=params)
    return client.json_or_text(resp)  # type: ignore[return-value]


def esummary(id_list: List[str], api_key: Optional[str] = None) -> Dict[str, Any]:
    client = HttpClient(requests_per_second=10.0 if api_key else 3.0)
    params = {
        "db": "pmc",
        "id": ",".join(id_list),
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key
    resp = client.get(f"{EUTILS_BASE}/esummary.fcgi", params=params)
    return client.json_or_text(resp)  # type: ignore[return-value]


def fetch_sample(term: str = "clinical trial AND cancer", retmax: int = 50, api_key: Optional[str] = None, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    search = esearch(term=term, retmax=retmax, api_key=api_key)
    ids: List[str] = search.get("esearchresult", {}).get("idlist", [])
    summaries = esummary(ids[:retmax], api_key=api_key) if ids else {"result": {}}

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "pmc_esearch.json", str(search))
        write_text(Path(save_dir) / "pmc_esummary.json", str(summaries))

    return {"search": search, "summary": summaries}


if __name__ == "__main__":
    out = Path("data/raw/pmc")
    result = fetch_sample(save_dir=out)
    print(f"Fetched {len(result.get('search', {}).get('esearchresult', {}).get('idlist', []))} PMC IDs")


