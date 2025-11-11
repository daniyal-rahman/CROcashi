from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader, pubmed_id_extractor


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def esearch(term: str, retmax: int = 50, api_key: Optional[str] = None) -> Dict[str, Any]:
    client = HttpClient(requests_per_second=10.0 if api_key else 3.0)
    params = {
        "db": "pubmed",
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
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key
    resp = client.get(f"{EUTILS_BASE}/esummary.fcgi", params=params)
    return client.json_or_text(resp)  # type: ignore[return-value]


def fetch_sample(
    term: str = "clinical trial AND cancer",
    retmax: int = 50,
    api_key: Optional[str] = None,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True,
    days_back: Optional[int] = None
) -> Dict[str, Any]:
    """
    Fetch publications from PubMed.
    
    Args:
        term: Search query
        retmax: Number of results to fetch
        api_key: NCBI API key (optional)
        save_dir: Optional directory to save raw JSON
        load_to_staging: Whether to load data into staging table (default: True)
        days_back: Optional number of days to look back (filters by publication date)
        
    Returns:
        Dict with search and summary results
    """
    from datetime import date, timedelta
    
    # Add date filter to search term if specified
    search_term = term
    if days_back:
        cutoff_date = (date.today() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        # PubMed date filter format: [PDAT]YYYY/MM/DD:YYYY/MM/DD
        today_str = date.today().strftime("%Y/%m/%d")
        search_term = f"{term} AND ({cutoff_date}:{today_str}[PDAT])"
    
    search = esearch(term=search_term, retmax=retmax, api_key=api_key)
    ids: List[str] = search.get("esearchresult", {}).get("idlist", [])
    summaries = esummary(ids[:retmax], api_key=api_key) if ids else {"result": {}}

    # Save to file if requested
    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "pubmed_esearch.json", str(search))
        write_text(Path(save_dir) / "pubmed_esummary.json", str(summaries))

    # Load to staging table for processing
    if load_to_staging and summaries.get('result'):
        loader = StagingLoader('pubmed')
        # Convert summary result dict to list of records
        result = summaries['result']
        records = []
        for pmid, data in result.items():
            if pmid != 'uids' and isinstance(data, dict):
                data['pmid'] = pmid  # Ensure pmid is in the record
                records.append(data)
        
        if records:
            stats = loader.load_records(
                records,
                id_extractor=pubmed_id_extractor,
                skip_duplicates=True
            )
            print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")

    return {"search": search, "summary": summaries}


if __name__ == "__main__":
    out = Path("data/raw/pubmed")
    result = fetch_sample(save_dir=out, load_to_staging=True)
    print(f"Fetched {len(result.get('search', {}).get('esearchresult', {}).get('idlist', []))} PubMed IDs")


