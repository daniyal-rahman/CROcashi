"""
USPTO Patent API Client

Client for fetching US patent data from USPTO APIs with rate limiting,
caching, and robust error handling. Follows patterns from sec_filings.py.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Iterator, Tuple
from urllib.parse import urljoin, quote_plus
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .patent_types import (
    PatentRecord, PatentSearchQuery, USPTO_API_BASE,
    USPTO_BULK_DATA_BASE, PHARMACEUTICAL_CPC_CLASSES
)

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for USPTO API calls."""
    
    def __init__(self, requests_per_minute: int = 120):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self.last_request_time = 0.0
    
    def wait_if_needed(self):
        """Wait if necessary to respect rate limits."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()


class USPTOPatentClient:
    """
    Client for USPTO patent data with caching and rate limiting.
    
    Features:
    - Rate limiting (120 requests/minute USPTO limit)
    - Intelligent caching with TTL
    - Robust error handling and retries
    - Support for both API and bulk data
    - Focus on US patents only
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize USPTO client.
        
        Args:
            config: Configuration dictionary with API settings
        """
        self.config = config or {}
        
        # API configuration
        self.api_base = self.config.get("api_base", USPTO_API_BASE)
        self.bulk_base = self.config.get("bulk_base", USPTO_BULK_DATA_BASE)
        self.timeout = self.config.get("timeout_seconds", 60)
        
        # Rate limiting
        rpm = self.config.get("rate_limit_rpm", 120)
        self.rate_limiter = RateLimiter(rpm)
        
        # Caching
        cache_dir = self.config.get("cache_dir", "data/uspto_cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_days = self.config.get("cache_ttl_days", 30)
        
        # HTTP session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=self.config.get("retry_attempts", 3),
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set user agent
        self.session.headers.update({
            'User-Agent': 'CROcashi-Patent-Client/1.0 (Research Use)'
        })
        
        logger.info(f"Initialized USPTO client with cache dir: {self.cache_dir}")
    
    def search_patents(self, query: PatentSearchQuery) -> List[PatentRecord]:
        """
        Search for patents using USPTO API.
        
        Args:
            query: Search parameters
            
        Returns:
            List of patent records matching the query
        """
        logger.info(f"Searching patents with query: {query}")
        
        # Check cache first
        cache_key = self._get_search_cache_key(query)
        cached_results = self._get_cached_search(cache_key)
        if cached_results:
            logger.info(f"Using cached search results for {cache_key}")
            return cached_results
        
        try:
            # Convert to USPTO API format
            api_query = query.to_uspto_query()
            
            # Perform search
            results = self._execute_patent_search(api_query, query.max_results)
            
            # Filter for pharmaceuticals if requested
            if query.pharmaceutical_only:
                results = [p for p in results if p.is_pharmaceutical]
            
            # Cache results
            self._cache_search_results(cache_key, results)
            
            logger.info(f"Found {len(results)} patents for query")
            return results
            
        except Exception as e:
            logger.error(f"Error searching patents: {e}")
            return []
    
    def fetch_patent_by_number(self, patent_number: str) -> Optional[PatentRecord]:
        """
        Fetch a specific patent by number.
        
        Args:
            patent_number: US patent number (e.g., "US10123456B2")
            
        Returns:
            Patent record or None if not found
        """
        logger.debug(f"Fetching patent: {patent_number}")
        
        # Check cache first
        cache_file = self.cache_dir / f"patent_{patent_number}.json"
        if self._is_cache_valid(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    return PatentRecord(**data)
            except Exception as e:
                logger.warning(f"Failed to load cached patent {patent_number}: {e}")
        
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            # Normalize patent number
            normalized_number = self._normalize_patent_number(patent_number)
            
            # Fetch from API
            url = f"{self.api_base}/patents/{normalized_number}"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # Parse response
            patent_data = response.json()
            patent_record = self._parse_patent_response(patent_data)
            
            # Cache the result
            with open(cache_file, 'w') as f:
                json.dump(patent_record.__dict__, f, default=str, indent=2)
            
            return patent_record
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Patent not found: {patent_number}")
                return None
            logger.error(f"HTTP error fetching patent {patent_number}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching patent {patent_number}: {e}")
            return None
    
    def fetch_patents_by_assignee(self, assignee_name: str, 
                                 since_date: Optional[date] = None,
                                 max_patents: int = 1000) -> List[PatentRecord]:
        """
        Fetch patents for a specific assignee.
        
        Args:
            assignee_name: Name of assignee to search for
            since_date: Only return patents granted since this date
            max_patents: Maximum number of patents to return
            
        Returns:
            List of patent records for the assignee
        """
        logger.info(f"Fetching patents for assignee: {assignee_name}")
        
        # Build search query
        query = PatentSearchQuery(
            assignee=assignee_name,
            grant_date_start=since_date,
            max_results=max_patents,
            pharmaceutical_only=True  # Focus on pharma patents
        )
        
        return self.search_patents(query)
    
    def fetch_pharmaceutical_patents(self, since_date: Optional[date] = None,
                                   max_patents: int = 5000) -> List[PatentRecord]:
        """
        Fetch recent pharmaceutical patents.
        
        Args:
            since_date: Only return patents since this date
            max_patents: Maximum number of patents to return
            
        Returns:
            List of pharmaceutical patent records
        """
        logger.info("Fetching pharmaceutical patents")
        
        # Build query for pharmaceutical patents
        query = PatentSearchQuery(
            cpc_classes=PHARMACEUTICAL_CPC_CLASSES,
            grant_date_start=since_date,
            max_results=max_patents,
            pharmaceutical_only=True
        )
        
        return self.search_patents(query)
    
    def _execute_patent_search(self, api_query: str, max_results: int) -> List[PatentRecord]:
        """Execute patent search against USPTO API."""
        results = []
        page_size = min(100, max_results)  # USPTO API page limit
        page = 0
        
        while len(results) < max_results:
            try:
                # Rate limiting
                self.rate_limiter.wait_if_needed()
                
                # Build API request
                url = f"{self.api_base}/patents/search"
                params = {
                    'q': api_query,
                    'limit': page_size,
                    'offset': page * page_size,
                    'format': 'json'
                }
                
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                
                data = response.json()
                patents = data.get('patents', [])
                
                # Parse each patent
                for patent_data in patents:
                    try:
                        patent_record = self._parse_patent_response(patent_data)
                        results.append(patent_record)
                        
                        if len(results) >= max_results:
                            break
                    except Exception as e:
                        logger.warning(f"Failed to parse patent: {e}")
                        continue
                
                # Check if we have more pages
                total_count = data.get('total_count', 0)
                if len(results) >= total_count or len(patents) < page_size:
                    break
                
                page += 1
                
            except Exception as e:
                logger.error(f"Error in patent search page {page}: {e}")
                break
        
        return results[:max_results]
    
    def _parse_patent_response(self, patent_data: Dict[str, Any]) -> PatentRecord:
        """Parse USPTO API response into PatentRecord."""
        
        def safe_date(date_str: Optional[str]) -> Optional[date]:
            """Safely parse date string."""
            if not date_str:
                return None
            try:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
            except:
                return None
        
        return PatentRecord(
            patent_number=patent_data.get('patent_number', ''),
            patent_id=patent_data.get('patent_id', ''),
            application_number=patent_data.get('application_number', ''),
            
            application_date=safe_date(patent_data.get('application_date')),
            grant_date=safe_date(patent_data.get('grant_date')),
            publication_date=safe_date(patent_data.get('publication_date')),
            priority_date=safe_date(patent_data.get('priority_date')),
            
            title=patent_data.get('title'),
            abstract=patent_data.get('abstract'),
            claims=patent_data.get('claims', []),
            description=patent_data.get('description'),
            
            cpc_classes=patent_data.get('cpc_classes', []),
            uspc_classes=patent_data.get('uspc_classes', []),
            
            inventors=patent_data.get('inventors', []),
            assignees=patent_data.get('assignees', []),
            applicants=patent_data.get('applicants', []),
            
            patent_status=patent_data.get('status'),
            patent_type=patent_data.get('type', 'utility'),
            
            cited_patents=patent_data.get('cited_patents', []),
            citing_patents=patent_data.get('citing_patents', []),
            non_patent_references=patent_data.get('non_patent_references', []),
            
            family_id=patent_data.get('family_id'),
            continuation_data=patent_data.get('continuation_data', {}),
            
            source_url=patent_data.get('url'),
            extracted_at=datetime.now(UTC)
        )
    
    def _normalize_patent_number(self, patent_number: str) -> str:
        """Normalize patent number for API queries."""
        # Remove common prefixes and format consistently
        number = patent_number.replace('US', '').replace('us', '')
        number = number.replace(',', '').replace(' ', '')
        
        # Ensure it looks like a patent number
        if not number.isdigit() and not any(c in number for c in ['A', 'B', 'C']):
            raise ValueError(f"Invalid patent number format: {patent_number}")
        
        return number
    
    def _get_search_cache_key(self, query: PatentSearchQuery) -> str:
        """Generate cache key for search query."""
        query_str = f"{query.assignee or ''}_{query.inventor or ''}"
        query_str += f"_{query.application_date_start or ''}_{query.max_results}"
        query_str += f"_{query.pharmaceutical_only}"
        
        # Create a hash for the cache key
        import hashlib
        return hashlib.md5(query_str.encode()).hexdigest()[:16]
    
    def _get_cached_search(self, cache_key: str) -> Optional[List[PatentRecord]]:
        """Get cached search results."""
        cache_file = self.cache_dir / f"search_{cache_key}.json"
        
        if not self._is_cache_valid(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                return [PatentRecord(**item) for item in data]
        except Exception as e:
            logger.warning(f"Failed to load cached search {cache_key}: {e}")
            return None
    
    def _cache_search_results(self, cache_key: str, results: List[PatentRecord]):
        """Cache search results."""
        cache_file = self.cache_dir / f"search_{cache_key}.json"
        
        try:
            data = [result.__dict__ for result in results]
            with open(cache_file, 'w') as f:
                json.dump(data, f, default=str, indent=2)
        except Exception as e:
            logger.warning(f"Failed to cache search results {cache_key}: {e}")
    
    def _is_cache_valid(self, cache_file: Path) -> bool:
        """Check if cache file is valid and not expired."""
        if not cache_file.exists():
            return False
        
        try:
            stat = cache_file.stat()
            age_days = (datetime.now().timestamp() - stat.st_mtime) / 86400
            return age_days < self.cache_ttl_days
        except:
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.cache_dir.exists():
            return {"cache_enabled": False}
        
        cache_files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)
        
        return {
            "cache_enabled": True,
            "cache_dir": str(self.cache_dir),
            "total_files": len(cache_files),
            "total_size_mb": total_size / 1024 / 1024,
            "ttl_days": self.cache_ttl_days
        }
    
    def clear_cache(self, older_than_days: Optional[int] = None):
        """Clear cache files."""
        if not self.cache_dir.exists():
            return
        
        cutoff_time = None
        if older_than_days:
            cutoff_time = datetime.now().timestamp() - (older_than_days * 86400)
        
        removed_count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                if cutoff_time is None or cache_file.stat().st_mtime < cutoff_time:
                    cache_file.unlink()
                    removed_count += 1
            except Exception as e:
                logger.warning(f"Failed to remove cache file {cache_file}: {e}")
        
        logger.info(f"Removed {removed_count} cache files")
