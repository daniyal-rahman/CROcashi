"""
PatentsView API client for fetching USPTO patent data.

Uses the new PatentSearch API 2.x (search.patentsview.org).
Documentation: https://search.patentsview.org/docs/

NOTE: The new API requires an API key. Request one at:
https://patentsview-support.atlassian.net/servicedesk/customer/portal/1/group/1/create/18
"""
import json
import os
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.utils.files import ensure_dir, write_text
from ingestion.utils.http import HttpClient
from ingestion.utils.staging_loader import StagingLoader, patentsview_id_extractor

# New PatentSearch API 2.x base URL
API_BASE = "https://search.patentsview.org/api/v1/patent/"

# Environment variable for API key
API_KEY_ENV = "PATENTSVIEW_API_KEY"


def get_api_key() -> Optional[str]:
    """Get PatentsView API key from environment variable."""
    return os.environ.get(API_KEY_ENV)


def search_patents(
    query: Optional[str] = None,
    limit: int = 50,
    date_from: str = "2020-01-01",
    date_to: Optional[str] = None,
    assignee_filter: Optional[str] = None,
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search USPTO PatentSearch API 2.x.

    Args:
        query: Optional JSON query string (overrides date_from/assignee_filter)
        limit: Number of results to fetch (max 1000 per request)
        date_from: Start date for patent_date filter (YYYY-MM-DD)
        date_to: End date for patent_date filter (YYYY-MM-DD)
        assignee_filter: Filter by assignee organization name
        save_dir: Optional directory to save raw JSON
        load_to_staging: Whether to load data into staging table (default: True)
        api_key: Optional API key (falls back to environment variable)

    Returns:
        Dict with fetched data including 'patents' key

    Raises:
        ValueError: If no API key is provided
    """
    # Get API key
    key = api_key or get_api_key()
    if not key:
        return {
            "error": True,
            "message": f"PatentsView API key required. Set {API_KEY_ENV} environment variable or request a key at: https://patentsview-support.atlassian.net/servicedesk/customer/portal/1/group/1/create/18",
            "patents": []
        }

    client = HttpClient(requests_per_second=0.75)  # 45/min = 0.75/sec

    # Build query if not provided
    if query is None:
        query_parts = []

        # Date range filter
        if date_from:
            query_parts.append({"_gte": {"patent_date": date_from}})
        if date_to:
            query_parts.append({"_lte": {"patent_date": date_to}})

        # Assignee filter (for pharmaceutical companies)
        if assignee_filter:
            query_parts.append({"_text_any": {"assignees.assignee_organization": assignee_filter}})

        # Combine with _and if multiple parts
        if len(query_parts) > 1:
            query = json.dumps({"_and": query_parts})
        elif len(query_parts) == 1:
            query = json.dumps(query_parts[0])
        else:
            # Default: patents from 2020 onwards
            query = json.dumps({"_gte": {"patent_date": "2020-01-01"}})

    # Build request parameters
    # Field list for patent data (adjusted for new API field names)
    fields = json.dumps([
        "patent_id",
        "patent_date",
        "patent_title",
        "patent_type",
        "patent_num_claims",
        "assignees.assignee_organization",
        "assignees.assignee_type",
        "inventors.inventor_name_first",
        "inventors.inventor_name_last"
    ])

    # Pagination options
    options = json.dumps({"size": min(limit, 1000)})

    # Construct URL with query parameters
    params = urllib.parse.urlencode({
        "q": query,
        "f": fields,
        "o": options
    })
    url = f"{API_BASE}?{params}"

    # Make request with API key header
    headers = {
        "X-Api-Key": key,
        "Accept": "application/json",
        **client.default_headers
    }

    try:
        resp = client.session.get(url, headers=headers, timeout=client.timeout_seconds)
        data = client.json_or_text(resp)
    except Exception as e:
        return {
            "error": True,
            "message": f"PatentsView API request failed: {str(e)}",
            "patents": []
        }

    # Handle API errors
    if isinstance(data, dict) and data.get("error"):
        error_msg = data.get("message", data.get("reason", "Unknown error"))
        print(f"PatentsView API error: {error_msg}")
        return {"error": True, "message": error_msg, "patents": []}

    # Normalize response format
    # New API returns data in 'patents' key with different field names
    patents = []
    if isinstance(data, dict):
        raw_patents = data.get("patents", [])

        # Transform to consistent format for downstream processing
        for p in raw_patents:
            patent = {
                "patent_number": p.get("patent_id", ""),
                "patent_date": p.get("patent_date", ""),
                "title": p.get("patent_title", ""),
                "patent_type": p.get("patent_type", ""),
                "num_claims": p.get("patent_num_claims", 0),
            }

            # Extract assignee organizations
            assignees = p.get("assignees", [])
            if assignees:
                # Take first organization assignee
                for assignee in assignees:
                    org = assignee.get("assignee_organization")
                    if org:
                        patent["assignee_organization"] = org
                        patent["assignee_type"] = assignee.get("assignee_type", "")
                        break

            # Extract inventors
            inventors = p.get("inventors", [])
            if inventors:
                inventor_names = []
                for inv in inventors:
                    first = inv.get("inventor_name_first", "")
                    last = inv.get("inventor_name_last", "")
                    if first or last:
                        inventor_names.append(f"{first} {last}".strip())
                patent["inventors"] = inventor_names

            patents.append(patent)

    result = {
        "error": False,
        "count": len(patents),
        "total_hits": data.get("total_hits", len(patents)) if isinstance(data, dict) else len(patents),
        "patents": patents
    }

    # Save to file if requested
    if save_dir is not None:
        ensure_dir(save_dir)
        write_text(Path(save_dir) / "patentsview_search.json", json.dumps(result, indent=2))

    # Load to staging table for processing
    if load_to_staging and patents:
        loader = StagingLoader('patentsview')
        stats = loader.load_records(
            patents,
            id_extractor=patentsview_id_extractor,
            skip_duplicates=True
        )
        print(f"Staging: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")

    return result


def search_pharma_patents(
    limit: int = 100,
    date_from: str = "2020-01-01",
    save_dir: Optional[Path] = None,
    load_to_staging: bool = True,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for pharmaceutical-related patents.

    Uses text search on patent titles for common pharmaceutical terms.

    Args:
        limit: Number of results to fetch
        date_from: Start date for patent_date filter
        save_dir: Optional directory to save raw JSON
        load_to_staging: Whether to load data into staging table
        api_key: Optional API key

    Returns:
        Dict with fetched data
    """
    # Query for pharmaceutical patents using text search
    # Search for common pharma-related terms in title
    pharma_terms = "pharmaceutical drug therapy treatment compound"
    query = json.dumps({
        "_and": [
            {"_gte": {"patent_date": date_from}},
            {"_text_any": {"patent_title": pharma_terms}}
        ]
    })

    return search_patents(
        query=query,
        limit=limit,
        save_dir=save_dir,
        load_to_staging=load_to_staging,
        api_key=api_key
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch patents from PatentsView API")
    parser.add_argument("--limit", type=int, default=50, help="Number of patents to fetch")
    parser.add_argument("--date-from", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--pharma", action="store_true", help="Search for pharma patents only")
    parser.add_argument("--save-dir", type=Path, help="Directory to save JSON output")
    parser.add_argument("--no-staging", action="store_true", help="Skip loading to staging table")
    parser.add_argument("--api-key", help="PatentsView API key (or set PATENTSVIEW_API_KEY env var)")

    args = parser.parse_args()

    if args.pharma:
        result = search_pharma_patents(
            limit=args.limit,
            date_from=args.date_from,
            save_dir=args.save_dir or Path("data/raw/patentsview"),
            load_to_staging=not args.no_staging,
            api_key=args.api_key
        )
    else:
        result = search_patents(
            limit=args.limit,
            date_from=args.date_from,
            save_dir=args.save_dir or Path("data/raw/patentsview"),
            load_to_staging=not args.no_staging,
            api_key=args.api_key
        )

    if result.get("error"):
        print(f"Error: {result.get('message')}")
    else:
        print(f"Fetched {result.get('count', 0)} patents (total: {result.get('total_hits', 0)})")
