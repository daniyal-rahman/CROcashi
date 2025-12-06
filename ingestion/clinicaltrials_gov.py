import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader, clinicaltrials_id_extractor


API_BASE = "https://clinicaltrials.gov/api/v2/studies"

logger = logging.getLogger(__name__)


def fetch_studies_sample(
    query_term: str = "cancer",
    page_size: int = 50,
    save_dir: Optional[Path] = None,
    requests_per_second: float = 3.0,
    load_to_staging: bool = True,
    days_back: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch clinical trials from ClinicalTrials.gov.
    
    Args:
        query_term: Search query
        page_size: Number of results to fetch
        save_dir: Optional directory to save raw JSON
        requests_per_second: Rate limit
        load_to_staging: Whether to load data into staging table (default: True)
        days_back: Optional number of days to look back (filters by last updated date)
        
    Returns:
        Dict with fetched data
    """
    from datetime import date, timedelta
    
    client = HttpClient(requests_per_second=requests_per_second)
    params: Dict[str, Any] = {
        "query.term": query_term,
        "pageSize": page_size,
        "countTotal": "true",
    }
    
    # Add date filter if specified
    if days_back:
        cutoff_date = (date.today() - timedelta(days=days_back)).isoformat()
        # ClinicalTrials.gov API supports filtering by last update date
        # Format: query.cond=AREA[LastUpdatePostDate]RANGE[2024-01-01,MAX]
        params["query.cond"] = f"AREA[LastUpdatePostDate]RANGE[{cutoff_date},MAX]"
    
    resp = client.get(API_BASE, params=params)
    data = client.json_or_text(resp)

    # Save to file if requested
    if save_dir is not None:
        ensure_dir(save_dir)
        output = Path(save_dir) / "clinicaltrials_gov_sample.json"
        write_text(output, resp.text)

    # Load to staging table for processing
    if load_to_staging and isinstance(data, dict) and 'studies' in data:
        loader = StagingLoader('clinicaltrials_gov')
        stats = loader.load_records(
            data['studies'],
            id_extractor=clinicaltrials_id_extractor,
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")

    return data  # type: ignore[return-value]


def fetch_studies_page(
    client: HttpClient,
    params: Dict[str, Any],
    page_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch a single page of studies from ClinicalTrials.gov API.
    
    Args:
        client: HttpClient instance
        params: Base query parameters
        page_token: Optional pagination token for fetching next page
        
    Returns:
        Dict with API response including studies and nextPageToken
    """
    request_params = params.copy()
    if page_token:
        request_params["pageToken"] = page_token
    
    resp = client.get(API_BASE, params=request_params)
    return client.json_or_text(resp)


def build_filter_query(
    phases: Optional[List[str]] = None,
    start_date_min: Optional[str] = None,
    start_date_max: Optional[str] = None,
    statuses: Optional[List[str]] = None,
) -> str:
    """
    Build a filter.advanced query string for ClinicalTrials.gov API v2.
    
    Args:
        phases: List of phases (e.g., ["PHASE2", "PHASE3"])
        start_date_min: Minimum start date in YYYY-MM-DD format
        start_date_max: Maximum start date in YYYY-MM-DD format
        statuses: List of statuses to filter (None = all statuses)
        
    Returns:
        Filter query string for filter.advanced parameter
    """
    filters = []
    
    # Phase filter
    if phases:
        phase_values = " OR ".join(phases)
        filters.append(f"AREA[Phase]({phase_values})")
    
    # Date range filter
    if start_date_min or start_date_max:
        min_date = start_date_min or "MIN"
        max_date = start_date_max or "MAX"
        filters.append(f"AREA[StartDate]RANGE[{min_date},{max_date}]")
    
    # Status filter (optional - if None, all statuses included)
    if statuses:
        status_values = " OR ".join(statuses)
        filters.append(f"AREA[OverallStatus]({status_values})")
    
    return " AND ".join(filters) if filters else ""


def fetch_studies_bulk(
    phases: Optional[List[str]] = None,
    start_date_min: Optional[str] = None,
    start_date_max: Optional[str] = None,
    statuses: Optional[List[str]] = None,
    page_size: int = 1000,
    max_studies: Optional[int] = None,
    requests_per_second: float = 3.0,
    load_to_staging: bool = True,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    save_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Fetch clinical trials in bulk with pagination and filtering.
    
    This function supports paginating through large result sets and filtering
    by phase, date range, and status.
    
    Args:
        phases: List of phases to filter (e.g., ["PHASE2", "PHASE3"])
                Use API v2 values: PHASE1, PHASE2, PHASE3, PHASE4, EARLY_PHASE1, NA
        start_date_min: Minimum start date (YYYY-MM-DD)
        start_date_max: Maximum start date (YYYY-MM-DD)
        statuses: List of statuses to filter (None = all statuses)
                  Valid values: RECRUITING, ACTIVE_NOT_RECRUITING, COMPLETED, 
                  ENROLLING_BY_INVITATION, NOT_YET_RECRUITING, SUSPENDED, 
                  TERMINATED, WITHDRAWN, AVAILABLE, NO_LONGER_AVAILABLE, 
                  TEMPORARILY_NOT_AVAILABLE, APPROVED_FOR_MARKETING, WITHHELD, UNKNOWN
        page_size: Number of studies per page (max 1000)
        max_studies: Optional maximum number of studies to fetch
        requests_per_second: Rate limit for API requests
        load_to_staging: Whether to load data into staging table
        progress_callback: Optional callback function(fetched_count, total_count)
        save_dir: Optional directory to save raw JSON responses
        
    Returns:
        Dict with statistics:
            - total_fetched: Total number of studies fetched
            - total_available: Total number of matching studies in API
            - pages_fetched: Number of pages retrieved
            - staging_stats: Dict with inserted/skipped/errors counts
    """
    client = HttpClient(requests_per_second=requests_per_second)
    
    # Build query parameters
    params: Dict[str, Any] = {
        "pageSize": min(page_size, 1000),  # API max is 1000
        "countTotal": "true",
    }
    
    # Build filter query
    filter_query = build_filter_query(
        phases=phases,
        start_date_min=start_date_min,
        start_date_max=start_date_max,
        statuses=statuses,
    )
    
    if filter_query:
        params["filter.advanced"] = filter_query
    
    logger.info(f"Starting bulk fetch with filter: {filter_query or 'none'}")
    
    # Initialize tracking
    all_studies: List[Dict[str, Any]] = []
    staging_stats = {'inserted': 0, 'skipped': 0, 'errors': 0}
    page_token = None
    pages_fetched = 0
    total_available = 0
    
    # Initialize staging loader
    loader = StagingLoader('clinicaltrials_gov') if load_to_staging else None
    
    # Save directory setup
    if save_dir:
        ensure_dir(save_dir)
    
    while True:
        try:
            # Fetch page
            logger.info(f"Fetching page {pages_fetched + 1}...")
            data = fetch_studies_page(client, params, page_token)
            
            if not isinstance(data, dict):
                logger.error(f"Unexpected response type: {type(data)}")
                break
            
            # Get total count on first page
            if pages_fetched == 0:
                total_available = data.get('totalCount', 0)
                logger.info(f"Total matching studies: {total_available}")
            
            # Get studies from response
            studies = data.get('studies', [])
            if not studies:
                logger.info("No more studies in response")
                break
            
            pages_fetched += 1
            all_studies.extend(studies)
            
            # Load to staging in batches
            if loader and studies:
                batch_stats = loader.load_records(
                    studies,
                    id_extractor=clinicaltrials_id_extractor,
                    skip_duplicates=True
                )
                staging_stats['inserted'] += batch_stats['inserted']
                staging_stats['skipped'] += batch_stats['skipped']
                staging_stats['errors'] += batch_stats['errors']
                
                logger.info(
                    f"Page {pages_fetched}: {len(studies)} studies "
                    f"(staging: +{batch_stats['inserted']} inserted, "
                    f"+{batch_stats['skipped']} skipped)"
                )
            
            # Save page to file if requested
            if save_dir:
                import json
                page_file = save_dir / f"page_{pages_fetched:04d}.json"
                write_text(page_file, json.dumps(data, indent=2, default=str))
            
            # Progress callback
            if progress_callback:
                progress_callback(len(all_studies), total_available)
            
            # Check if we've reached the limit
            if max_studies and len(all_studies) >= max_studies:
                logger.info(f"Reached max_studies limit ({max_studies})")
                break
            
            # Get next page token
            page_token = data.get('nextPageToken')
            if not page_token:
                logger.info("No more pages (no nextPageToken)")
                break
            
            # Brief pause between pages to be nice to the API
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error fetching page {pages_fetched + 1}: {e}")
            # Continue to next page on error
            if page_token:
                continue
            else:
                break
    
    # Trim to max_studies if specified
    if max_studies and len(all_studies) > max_studies:
        all_studies = all_studies[:max_studies]
    
    result = {
        'total_fetched': len(all_studies),
        'total_available': total_available,
        'pages_fetched': pages_fetched,
        'staging_stats': staging_stats,
        'filter_query': filter_query,
    }
    
    logger.info(
        f"Bulk fetch complete: {result['total_fetched']} studies fetched "
        f"from {result['pages_fetched']} pages "
        f"(total available: {result['total_available']})"
    )
    
    if load_to_staging:
        logger.info(
            f"Staging: {staging_stats['inserted']} inserted, "
            f"{staging_stats['skipped']} skipped, {staging_stats['errors']} errors"
        )
    
    return result


def fetch_phase_2_3_studies(
    start_year: int = 2018,
    end_year: int = 2024,
    max_studies: Optional[int] = None,
    load_to_staging: bool = True,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to fetch Phase 2/3 clinical trials for a date range.
    
    This is a wrapper around fetch_studies_bulk with preset parameters
    for Phase 2 and Phase 3 trials.
    
    Args:
        start_year: Start year (inclusive)
        end_year: End year (inclusive)
        max_studies: Optional maximum number of studies to fetch
        load_to_staging: Whether to load data into staging table
        progress_callback: Optional callback function(fetched_count, total_count)
        
    Returns:
        Dict with fetch statistics
    """
    return fetch_studies_bulk(
        phases=["PHASE2", "PHASE3"],
        start_date_min=f"{start_year}-01-01",
        start_date_max=f"{end_year}-12-31",
        statuses=None,  # All statuses
        page_size=1000,
        max_studies=max_studies,
        requests_per_second=3.0,
        load_to_staging=load_to_staging,
        progress_callback=progress_callback,
    )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch clinical trials from ClinicalTrials.gov')
    parser.add_argument('--bulk', action='store_true', help='Run bulk fetch instead of sample')
    parser.add_argument('--phases', nargs='+', default=['PHASE2', 'PHASE3'], help='Phases to fetch')
    parser.add_argument('--start-year', type=int, default=2018, help='Start year')
    parser.add_argument('--end-year', type=int, default=2024, help='End year')
    parser.add_argument('--max', type=int, default=None, help='Maximum studies to fetch')
    parser.add_argument('--save-dir', type=str, default=None, help='Directory to save raw JSON')
    
    args = parser.parse_args()
    
    if args.bulk:
        # Bulk fetch
        save_dir = Path(args.save_dir) if args.save_dir else None
        result = fetch_studies_bulk(
            phases=args.phases,
            start_date_min=f"{args.start_year}-01-01",
            start_date_max=f"{args.end_year}-12-31",
            max_studies=args.max,
            load_to_staging=True,
            save_dir=save_dir,
        )
        print(f"\nBulk fetch complete:")
        print(f"  Total fetched: {result['total_fetched']}")
        print(f"  Total available: {result['total_available']}")
        print(f"  Pages fetched: {result['pages_fetched']}")
        print(f"  Staging: {result['staging_stats']}")
    else:
        # Sample fetch (original behavior)
        out = Path("data/raw/clinicaltrials_gov")
        result = fetch_studies_sample(save_dir=out, load_to_staging=True)
        print(f"Fetched {len(result.get('studies', []))} studies (sample)")


