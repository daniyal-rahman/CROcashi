from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader, sec_filing_id_extractor
from ingestion.utils.biotech_companies import get_biotech_ciks


API_BASE = "https://data.sec.gov/api/xbrl/companyconcept"
SUBMISSIONS_API_BASE = "https://data.sec.gov/submissions"


def get_company_concept(cik: str, taxonomy: str = "us-gaap", tag: str = "", save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Get SEC EDGAR company concept data."""
    client = HttpClient(requests_per_second=1.0, user_agent="CROcashi-Ingestion contact@example.com")
    url = f"{API_BASE}/CIK{cik.zfill(10)}/{taxonomy}/{tag}.json" if tag else f"{API_BASE}/CIK{cik.zfill(10)}/{taxonomy}.json"
    resp = client.get(url)
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / f"sec_edgar_cik_{cik}.json", resp.text)

    return data  # type: ignore[return-value]


def search_company(name: str, save_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Search for a company in SEC EDGAR (via companytickers endpoint)."""
    client = HttpClient(requests_per_second=1.0, user_agent="CROcashi-Ingestion contact@example.com")
    resp = client.get("https://www.sec.gov/files/company_tickers.json")
    data = client.json_or_text(resp)

    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "sec_company_tickers.json", resp.text)

    return data  # type: ignore[return-value]


def fetch_8k_filings_by_cik(
    cik: str,
    limit: int = 50,
    load_to_staging: bool = True,
    requests_per_second: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Fetch 8-K filings for a specific company by CIK.
    
    Args:
        cik: Company CIK (with or without leading zeros)
        limit: Maximum number of filings to fetch
        load_to_staging: Whether to load data into staging table
        requests_per_second: Rate limit for API requests
        
    Returns:
        List of filing records
    """
    client = HttpClient(
        requests_per_second=requests_per_second,
        user_agent="CROcashi-Ingestion contact@example.com"
    )
    
    # Normalize CIK to 10-digit format
    cik_padded = str(int(cik)).zfill(10)
    
    # Fetch company submissions
    submissions_url = f"{SUBMISSIONS_API_BASE}/CIK{cik_padded}.json"
    resp = client.get(submissions_url)
    submissions_data = client.json_or_text(resp)
    
    if not isinstance(submissions_data, dict):
        print(f"Error: Invalid response for CIK {cik_padded}")
        return []
    
    # Extract company name
    company_name = submissions_data.get('name', 'Unknown Company')
    
    # Extract recent filings
    filings = submissions_data.get('filings', {})
    recent = filings.get('recent', {})
    
    if not recent:
        print(f"No recent filings found for CIK {cik_padded}")
        return []
    
    # Get filing arrays
    forms = recent.get('form', [])
    filing_dates = recent.get('filingDate', [])
    accession_numbers = recent.get('accessionNumber', [])
    primary_documents = recent.get('primaryDocument', [])
    
    # Filter for 8-K filings
    filing_records = []
    for i, form in enumerate(forms):
        if form and form.upper() in ['8-K', '8-K/A']:  # Include amended filings
            if i < len(accession_numbers) and i < len(filing_dates):
                accession_number = accession_numbers[i]
                filing_date = filing_dates[i]
                primary_doc = primary_documents[i] if i < len(primary_documents) else None
                
                # Create filing record
                filing_record = {
                    'cik': cik_padded,
                    'company_name': company_name,
                    'form': form,
                    'filing_date': filing_date,
                    'accessionNumber': accession_number,  # camelCase for staging loader
                    'accession_number': accession_number,  # snake_case for processor
                    'primary_document': primary_doc,
                    'filing_url': f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={cik_padded}&accession_number={accession_number.replace('-', '')}&xbrl_type=v"
                }
                
                filing_records.append(filing_record)
                
                if len(filing_records) >= limit:
                    break
    
    # Load to staging if requested
    if load_to_staging and filing_records:
        loader = StagingLoader('sec_edgar')
        stats = loader.load_records(
            filing_records,
            id_extractor=sec_filing_id_extractor,
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")
    
    return filing_records


def fetch_8k_filings_for_biotech_companies(
    cik_list: Optional[List[str]] = None,
    limit_per_company: int = 10,
    load_to_staging: bool = True,
    requests_per_second: float = 1.0
) -> List[Dict[str, Any]]:
    """
    Fetch 8-K filings for biotech/pharma companies.
    
    Args:
        cik_list: Optional list of CIKs to fetch. If None, uses get_biotech_ciks()
        limit_per_company: Maximum filings per company
        load_to_staging: Whether to load data into staging table
        requests_per_second: Rate limit for API requests
        
    Returns:
        List of all filing records
    """
    if cik_list is None:
        cik_list = get_biotech_ciks()
    
    all_filings = []
    
    for cik in cik_list:
        print(f"Fetching 8-K filings for CIK {cik}...")
        try:
            filings = fetch_8k_filings_by_cik(
                cik=cik,
                limit=limit_per_company,
                load_to_staging=load_to_staging,
                requests_per_second=requests_per_second
            )
            all_filings.extend(filings)
            print(f"  Found {len(filings)} filings")
        except Exception as e:
            print(f"  Error fetching filings for CIK {cik}: {e}")
            continue
    
    print(f"\nTotal filings fetched: {len(all_filings)}")
    return all_filings


def search_8k_filings(
    query: str = "biotechnology",
    limit: int = 50,
    load_to_staging: bool = True
) -> List[Dict[str, Any]]:
    """
    Search for 8-K filings using SEC full-text search.
    
    Note: SEC doesn't have a public full-text search API for filings.
    This function is a placeholder for future implementation.
    
    Args:
        query: Search query
        limit: Maximum results
        load_to_staging: Whether to load data into staging table
        
    Returns:
        List of filing records
    """
    # TODO: Implement SEC full-text search when API becomes available
    # For now, use biotech company list approach
    print("Note: SEC full-text search not yet implemented. Using biotech company list instead.")
    return fetch_8k_filings_for_biotech_companies(
        limit_per_company=limit // 10,  # Distribute limit across companies
        load_to_staging=load_to_staging
    )


if __name__ == "__main__":
    out = Path("data/raw/sec_edgar")
    tickers = search_company("", save_dir=out)
    print("Fetched SEC EDGAR company tickers")
    
    # Example: Fetch 8-K filings for Moderna (CIK: 1682852)
    print("\nFetching 8-K filings for Moderna...")
    moderna_filings = fetch_8k_filings_by_cik("1682852", limit=10, load_to_staging=True)
    print(f"Found {len(moderna_filings)} 8-K filings")

