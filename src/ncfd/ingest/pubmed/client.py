"""
PubMed E-utilities client implementation.

Provides batched, rate-limited access to PubMed APIs with retry logic and error handling.
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import re
import xml.etree.ElementTree as ET

import aiohttp
from aiohttp import ClientTimeout

from ...logging import get_logger, EventTaxonomy

logger = get_logger(__name__)


def _make_logging_safe(obj: Any) -> Any:
    """Convert objects to be safe for JSON serialization in logging."""
    if hasattr(obj, 'isoformat'):  # datetime object
        return obj.isoformat()
    elif isinstance(obj, (dict, list)):
        return str(obj)[:200]  # Truncate large objects
    elif obj is None:
        return None
    else:
        return str(obj)


class PubMedClient:
    """PubMed E-utilities API client with rate limiting and batching."""
    
    # API endpoints
    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_per_sec: int = 8,
        batch_size: int = 100,
        max_retries: int = 3,
        timeout_seconds: int = 30,
        backoff_base: float = 2.0,
        circuit_breaker_threshold: int = 5,
        email: str = "ncfd@example.com",
        tool: str = "NCFD"
    ):
        """
        Initialize PubMed client.
        
        Args:
            api_key: NCBI API key for higher rate limits
            rate_limit_per_sec: Maximum requests per second
            batch_size: Maximum PMIDs per request
            max_retries: Maximum retry attempts
            timeout_seconds: Request timeout
            backoff_base: Exponential backoff base
            circuit_breaker_threshold: Consecutive failures before circuit breaker
            email: Contact email for NCBI (required)
            tool: Tool name for NCBI (required)
        """
        self.api_key = api_key
        self.rate_limit_per_sec = max(1, rate_limit_per_sec)  # Ensure at least 1 req/sec
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = ClientTimeout(total=timeout_seconds)
        self.backoff_base = backoff_base
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.email = email
        self.tool = tool
        
        # Rate limiting
        self.min_delay = 1.0 / self.rate_limit_per_sec
        self.last_request_time = 0.0
        self._rate_limit_lock = asyncio.Lock()
        
        # Circuit breaker
        self.consecutive_failures = 0
        self.circuit_breaker_open = False
        self.circuit_breaker_open_until = None
        
        # Call counters
        self.esearch_calls = 0
        self.efetch_calls = 0
        self.esummary_calls = 0
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def _get_base_params(self) -> Dict[str, str]:
        """Get base parameters for all API calls."""
        params = {
            'tool': self.tool,
            'email': self.email,
            'retmode': 'json'
        }
        if self.api_key:
            params['api_key'] = self.api_key
        return params
    
    def _normalize_params(self, params: Dict[str, Any]) -> Dict[str, str]:
        """
        Normalize request parameters for PubMed E-utilities.
        
        Converts all values to strings that PubMed expects.
        
        Args:
            params: Raw parameters dictionary
            
        Returns:
            Normalized parameters dictionary with string values
        """
        normalized = {}
        
        for key, value in params.items():
            if value is None:
                continue  # Skip None values
            elif hasattr(value, 'strftime'):  # datetime or date object
                # Convert to E-utilities format (YYYY/MM/DD)
                normalized[key] = value.strftime('%Y/%m/%d')
            elif isinstance(value, bool):
                # Convert bool to "y"/"n"
                normalized[key] = 'y' if value else 'n'
            elif isinstance(value, (list, tuple)):
                # Convert lists to comma-separated strings
                normalized[key] = ','.join(str(item) for item in value)
            else:
                # Convert everything else to string
                normalized[key] = str(value)
        
        return normalized
    
    def _calculate_reldate_days(self, months: int) -> int:
        """
        Calculate reldate parameter for PubMed E-utilities.
        
        Args:
            months: Number of months for recency window
            
        Returns:
            Number of days for reldate parameter
        """
        # Use 30.44 days per month (365.25/12) for accuracy
        return int(months * 30.44)
    
    async def esearch_with_recency(
        self,
        query: str,
        recency_months: int = 18,
        max_results: int = 100,
        sort: str = "relevance",
        use_history: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute PubMed ESearch query with recency filter using reldate.
        
        Args:
            query: PubMed search query
            recency_months: Number of months for recency window (default: 18)
            max_results: Maximum number of results to return
            sort: Sort order
            use_history: Whether to use history for large result sets
            **kwargs: Additional query parameters
            
        Returns:
            Search results with PMIDs and count
        """
        # Add reldate parameter for recency filtering
        kwargs['reldate'] = self._calculate_reldate_days(recency_months)
        kwargs['datetype'] = 'pdat'  # Publication date
        
        return await self.esearch(
            query=query,
            max_results=max_results,
            sort=sort,
            use_history=use_history,
            **kwargs
        )
    
    async def esearch_all_with_recency(
        self,
        query: str,
        recency_months: int = 18,
        max_results: Optional[int] = None,
        sort: str = "relevance",
        use_history: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute PubMed ESearch query with pagination and recency filter.
        
        Args:
            query: PubMed search query
            recency_months: Number of months for recency window (default: 18)
            max_results: Maximum number of results to return
            sort: Sort order
            use_history: Whether to use history for large result sets
            **kwargs: Additional query parameters
            
        Returns:
            Complete search results with PMIDs, count, and history info
        """
        # Add reldate parameter for recency filtering
        kwargs['reldate'] = self._calculate_reldate_days(recency_months)
        kwargs['datetype'] = 'pdat'  # Publication date
        
        return await self.esearch_all(
            query=query,
            max_results=max_results,
            sort=sort,
            use_history=use_history,
            **kwargs
        )
    
    async def _rate_limit(self):
        """Ensure rate limiting is respected with proper locking."""
        async with self._rate_limit_lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            if time_since_last < self.min_delay:
                delay = self.min_delay - time_since_last
                await asyncio.sleep(delay)
            self.last_request_time = time.time()
    
    def _check_circuit_breaker(self):
        """Check if circuit breaker is open."""
        if self.circuit_breaker_open:
            if datetime.now(timezone.utc) < self.circuit_breaker_open_until:
                raise Exception("Circuit breaker is open - too many consecutive failures")
            else:
                self.circuit_breaker_open = False
                self.consecutive_failures = 0
    
    def _record_failure(self):
        """Record a failure and potentially open circuit breaker."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.circuit_breaker_threshold:
            self.circuit_breaker_open = True
            self.circuit_breaker_open_until = datetime.now(timezone.utc) + timedelta(minutes=1)
            logger.warn(
                EventTaxonomy.MONITORING_ALERT,
                f"Circuit breaker opened after {self.consecutive_failures} consecutive failures",
                consecutive_failures=self.consecutive_failures,
                circuit_breaker_threshold=self.circuit_breaker_threshold,
                circuit_breaker_open_until=self.circuit_breaker_open_until.isoformat() if self.circuit_breaker_open_until else None
            )
    
    def _record_success(self):
        """Record a successful request."""
        self.consecutive_failures = 0
    
    def _increment_call_counter(self, url: str):
        """Increment appropriate call counter based on URL."""
        if 'esearch' in url:
            self.esearch_calls += 1
        elif 'efetch' in url:
            self.efetch_calls += 1
        elif 'esummary' in url:
            self.esummary_calls += 1
    
    async def _make_request(
        self, 
        url: str, 
        params: Dict[str, Any],
        expect_json: bool = True
    ) -> Any:
        """
        Make HTTP request with retry logic and circuit breaker.
        
        Args:
            url: Request URL
            params: Query parameters
            expect_json: Whether to expect JSON response (default: True)
            
        Returns:
            Response data (JSON dict or text string)
            
        Raises:
            Exception: On circuit breaker or persistent failures
        """
        self._check_circuit_breaker()
        await self._rate_limit()
        
        # Normalize parameters to ensure all values are JSON-safe strings
        normalized_params = self._normalize_params(params)
        
        # Additional safety: ensure all params are strings and safe for aiohttp
        safe_params = {}
        for key, value in normalized_params.items():
            safe_params[str(key)] = str(value) if value is not None else None
        
        for attempt in range(self.max_retries):
            try:
                if not self.session:
                    raise Exception("Client session not initialized")
                    
                async with self.session.get(url, params=safe_params) as response:
                    if response.status == 429:  # Too Many Requests
                        retry_after_s = response.headers.get('Retry-After')
                        sleep_s = self._parse_retry_after(retry_after_s) if retry_after_s else 60
                        logger.warn(
                            EventTaxonomy.PUBMED_EFETCH_ERROR,
                            f"Rate limit hit (429); sleeping {sleep_s}s",
                            sleep_seconds=sleep_s,
                            retry_attempt=attempt,
                            max_retries=self.max_retries
                        )
                        await asyncio.sleep(sleep_s)
                        # Continue loop without extra backoff for this attempt
                        continue
                    
                    response.raise_for_status()
                    text = await response.text()
                    
                    if expect_json:
                        try:
                            result = json.loads(text)
                            self._record_success()
                            self._increment_call_counter(url)
                            return result
                        except json.JSONDecodeError as e:
                            logger.error(
                                EventTaxonomy.PUBMED_EFETCH_ERROR,
                                f"Failed to parse JSON response: {e}",
                                err_type=type(e).__name__,
                                err_msg=str(e),
                                response_text=response_text[:500] if response_text else None
                            )
                            logger.debug(f"Response text: {text[:500]}...")
                            raise
                    else:
                        # Return raw text for non-JSON responses
                        self._record_success()
                        self._increment_call_counter(url)
                        return text
                        
            except aiohttp.ClientResponseError as e:
                if e.status == 429:
                    # 429 handling is now done above in the response check
                    self._record_failure()
                    if attempt < self.max_retries - 1:
                        wait_time = self.backoff_base ** attempt
                        logger.warn(
                            EventTaxonomy.PUBMED_EFETCH_ERROR,
                            f"Rate limited, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})",
                            wait_time=wait_time,
                            retry_attempt=attempt + 1,
                            max_retries=self.max_retries,
                            err_type="RateLimitError"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    raise
                elif e.status >= 500:
                    self._record_failure()
                    if attempt < self.max_retries - 1:
                        wait_time = self.backoff_base ** attempt
                        logger.warn(
                            EventTaxonomy.PUBMED_EFETCH_ERROR,
                            f"Server error {e.status}, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})",
                            wait_time=wait_time,
                            retry_attempt=attempt + 1,
                            max_retries=self.max_retries,
                            err_type="ServerError",
                            status_code=e.status
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    raise
                else:
                    raise
            except Exception as e:
                self._record_failure()
                if attempt < self.max_retries - 1:
                    wait_time = self.backoff_base ** attempt
                    logger.warn(
                        EventTaxonomy.PUBMED_EFETCH_ERROR,
                        f"Request failed, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries}): {e}",
                        wait_time=wait_time,
                        retry_attempt=attempt + 1,
                        max_retries=self.max_retries,
                        err_type=type(e).__name__,
                        err_msg=str(e)
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise
        
        # If we get here, all retries failed
        raise Exception(f"Request failed after {self.max_retries} attempts")
    
    async def esearch(
        self, 
        query: str, 
        max_results: int = 100,
        sort: str = "relevance",
        use_history: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute PubMed ESearch query.
        
        Args:
            query: PubMed search query
            max_results: Maximum number of results to return
            sort: Sort order (relevance, pub_date, first_author, journal, title)
            use_history: Whether to use history for large result sets
            **kwargs: Additional query parameters (mindate, maxdate, reldate, etc.)
                     Datetime objects will be automatically converted to YYYY/MM/DD format
            
        Returns:
            Search results with PMIDs and count
        """
        params = self._get_base_params()
        params.update({
            'db': 'pubmed',
            'term': query,
            'retmax': min(max_results, self.batch_size),
            'sort': sort,
            'retmode': 'json'
        })
        
        if use_history:
            params['usehistory'] = 'y'
        
        # Add additional query parameters
        params.update(kwargs)
        
        # Create safe logging parameters
        log_params = {
            'query_preview': query[:200] if query else '',
            'max_results': max_results,
            'sort': sort,
            'use_history': use_history
        }
        
        # Add kwargs with safe serialization
        for key, value in kwargs.items():
            log_params[key] = _make_logging_safe(value)
        
        logger.info(f"🔍 PubMed Search: '{query[:50]}{'...' if len(query) > 50 else ''}' (max: {retmax})")
        
        start_time = time.time()
        result = await self._make_request(self.ESEARCH_URL, params)
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Extract result info
        esearch_result = result.get('esearchresult', {})
        count = int(esearch_result.get('count', 0))
        pmids = esearch_result.get('idlist', [])
        
        logger.info(f"✅ Found {count} documents")
        
        if 'esearchresult' not in result:
            raise Exception(f"Unexpected ESearch response format: {result}")
            
        return result['esearchresult']
    
    async def esearch_all(
        self, 
        query: str, 
        max_results: Optional[int] = None, 
        sort: str = "relevance", 
        use_history: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute PubMed ESearch query with pagination to get all results.
        
        Args:
            query: PubMed search query
            max_results: Maximum number of results to return
            sort: Sort order
            use_history: Whether to use history for large result sets
            **kwargs: Additional query parameters (mindate, maxdate, reldate, etc.)
                     Datetime objects will be automatically converted to YYYY/MM/DD format
            
        Returns:
            Complete search results with PMIDs, count, and history info
        """
        params = self._get_base_params()
        params.update({
            'db': 'pubmed',
            'term': query,
            'retmax': self.batch_size,
            'retstart': 0,
            'sort': sort,
            'retmode': 'json'
        })
        
        if use_history:
            params['usehistory'] = 'y'
        
        # Add additional query parameters
        params.update(kwargs)
        
        # Create safe logging parameters
        log_params = {
            'query_preview': query[:200] if query else '',
            'max_results': max_results,
            'sort': sort,
            'use_history': use_history
        }
        
        # Add kwargs with safe serialization
        for key, value in kwargs.items():
            log_params[key] = _make_logging_safe(value)
        
        logger.info(f"🔍 PubMed Paginated Search: '{query[:50]}{'...' if len(query) > 50 else ''}' (max: {max_results})")
        
        ids = []
        webenv = None
        query_key = None
        
        # Set default max_results if not provided
        if max_results is None:
            max_results = 1000
        
        while len(ids) < max_results:
            result = await self._make_request(self.ESEARCH_URL, params)
            esr = result['esearchresult']
            
            if use_history:
                webenv = esr.get('webenv')
                query_key = esr.get('querykey')
            
            batch_ids = esr.get('idlist', [])
            ids.extend(batch_ids)
            
            total_count = int(esr.get('count', '0'))
            if len(ids) >= total_count or len(ids) >= max_results:
                break
                
            params['retstart'] += self.batch_size
        
        return {
            'idlist': ids[:max_results],
            'webenv': webenv,
            'querykey': query_key,
            'count': len(ids[:max_results]),
            'total_count': total_count
        }
    
    async def esummary_batch(self, pmids: List[str]) -> Dict[str, Any]:
        """
        Fetch metadata for a batch of PMIDs.
        
        Args:
            pmids: List of PubMed IDs
            
        Returns:
            Metadata for each PMID (cleaned, no uids key)
        """
        if not pmids:
            return {}
            
        # Split into batches
        batches = [pmids[i:i + self.batch_size] for i in range(0, len(pmids), self.batch_size)]
        all_results = {}
        
        for batch in batches:
            params = self._get_base_params()
            params.update({
                'db': 'pubmed',
                'id': ','.join(batch),
                'retmode': 'json'
            })
            
            logger.info(f"📋 Fetching metadata for {len(batch)} documents")
            
            start_time = time.time()
            result = await self._make_request(self.ESUMMARY_URL, params)
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"✅ Got metadata for {len(batch)} documents")
            
            if 'result' in result:
                data = result['result']
                # Extract uids and remove from data
                uids = set(data.pop('uids', []))
                # Only keep PMID entries, not metadata
                batch_results = {uid: data[str(uid)] for uid in uids if str(uid) in data}
                all_results.update(batch_results)
        
        return all_results
    
    async def efetch_batch(
        self, 
        pmids: List[str], 
        rettype: str = "abstract"
    ) -> Dict[str, str]:
        """
        Fetch content for a batch of PMIDs.
        
        Args:
            pmids: List of PubMed IDs
            rettype: Return type (abstract, medline, xml)
            
        Returns:
            Content for each PMID
        """
        if not pmids:
            return {}
            
        # Split into batches
        batches = [pmids[i:i + self.batch_size] for i in range(0, len(pmids), self.batch_size)]
        all_results = {}
        
        for batch in batches:
            params = self._get_base_params()
            params.update({
                'db': 'pubmed',
                'id': ','.join(batch),
                'rettype': rettype,
                'retmode': 'text'  # Force text mode for content
            })
            
            logger.info(f"📄 Fetching {rettype} for {len(batch)} documents")
            
            start_time = time.time()
            result = await self._make_request(self.EFETCH_URL, params, expect_json=False)
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(f"✅ Got {rettype} for {len(batch)} documents")
            
            # EFetch returns text content, not JSON
            if isinstance(result, str):
                # Parse the text response to extract individual abstracts
                content_map = self._parse_efetch_response(result, batch, rettype)
                all_results.update(content_map)
            else:
                logger.warning(f"Unexpected EFetch response type: {type(result)}")
        
        return all_results
    
    async def efetch_abstracts_xml(self, pmids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch abstracts in XML format for more reliable parsing, including PMCID detection.
        
        Args:
            pmids: List of PubMed IDs
            
        Returns:
            Dictionary mapping PMID to document info (abstract, pmcid, has_free_full_text)
        """
        if not pmids:
            return {}
            
        # Split into batches
        batches = [pmids[i:i + self.batch_size] for i in range(0, len(pmids), self.batch_size)]
        all_results = {}
        
        for batch in batches:
            params = self._get_base_params()
            params.update({
                'db': 'pubmed',
                'id': ','.join(batch),
                'retmode': 'xml'
            })
            
            logger.info(f"📄 Fetching abstracts for {len(batch)} documents")
            result = await self._make_request(self.EFETCH_URL, params, expect_json=False)
            
            if isinstance(result, str):
                # Parse XML response
                content_map = self._parse_xml_response(result, batch)
                all_results.update(content_map)
            else:
                logger.warning(f"Unexpected EFetch XML response type: {type(result)}")
        
        return all_results
    
    
    def _parse_xml_response(self, xml_text: str, pmids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Parse XML response to extract PMIDs, abstracts, and PMCID information.
        
        Args:
            xml_text: Raw XML response
            pmids: List of PMIDs that were requested
            
        Returns:
            Dictionary mapping PMID to document info (abstract, pmcid, etc.)
        """
        # Prefill output with empty data for all requested PMIDs
        pmid_set = set(pmids)
        content_map = {pmid: {"abstract": "", "pmcid": None, "has_free_full_text": False} for pmid in pmids}
        
        try:
            # Parse XML response
            root = ET.fromstring(xml_text)
            
            # Accept both possible XML structures
            articles = root.findall('.//PubmedArticle')
            if not articles and root.tag == 'PubmedArticleSet':
                articles = list(root)
            
            returned_pmids = set()
            pmcid_count = 0
            
            for article in articles:
                pmid_elem = article.find('.//PMID')
                if pmid_elem is not None and pmid_elem.text:
                    pmid = pmid_elem.text
                    returned_pmids.add(pmid)
                    if pmid in pmid_set:
                        # Extract abstract for this PMID
                        abstract_text = self._extract_full_abstract(article)
                        
                        # Extract PMCID
                        pmcid = self._extract_pmcid_from_article(article)
                        
                        # Determine if has free full text
                        has_free_full_text = bool(pmcid)  # PMCID = free full text
                        
                        content_map[pmid] = {
                            "abstract": abstract_text,
                            "pmcid": pmcid,
                            "has_free_full_text": has_free_full_text
                        }
                        
                        if pmcid:
                            pmcid_count += 1
            
            # Log missing PMIDs for debugging
            missing = pmid_set - returned_pmids
            if missing:
                logger.warning(f"EFetch returned {len(returned_pmids)}/{len(pmids)} PMIDs; missing: {sorted(missing)[:10]}")
            
            abstract_count = len([k for k, v in content_map.items() if v["abstract"]])
            logger.info(f"✅ Parsed {abstract_count}/{len(pmids)} abstracts, {pmcid_count}/{len(pmids)} PMCIDs")
            
        except ET.ParseError as e:
            logger.error(f"Failed to parse XML response: {e}")
            logger.debug(f"XML preview: {xml_text[:500]}...")
        except Exception as e:
            logger.error(f"Unexpected error parsing XML: {e}")
        
        return content_map
    
    def _parse_xml_stream(self, xml_text: str, pmid_set: set, content_map: Dict[str, str]) -> None:
        """
        Parse XML using stream parsing for memory efficiency.
        
        Args:
            xml_text: Raw XML response
            pmid_set: Set of PMIDs to look for
            content_map: Dictionary to populate with results
        """
        import io
        
        # Use iterparse for memory-efficient streaming
        context = ET.iterparse(io.StringIO(xml_text), events=('start', 'end'))
        context = iter(context)
        event, root = next(context)  # Get root element
        
        current_article = None
        current_pmid = None
        
        for event, elem in context:
            if event == 'start':
                if elem.tag == 'PubmedArticle':
                    current_article = elem
                    current_pmid = None
            elif event == 'end':
                if elem.tag == 'PMID' and current_article is not None:
                    # Found PMID within current article
                    pmid = elem.text
                    if pmid in pmid_set:
                        current_pmid = pmid
                        # Extract abstract for this PMID
                        abstract_text = self._extract_full_abstract(current_article)
                        if abstract_text:
                            content_map[pmid] = abstract_text
                        # else: already set to "" in prefill
                
                elif elem.tag == 'PubmedArticle':
                    # Finished processing this article, clear references
                    current_article = None
                    current_pmid = None
                
                # Clear element to free memory
                elem.clear()
    
    def _extract_full_abstract(self, article) -> str:
        """
        Extract full abstract text from article, handling multiple sections, nested tags,
        and preferring English abstracts.
        
        Args:
            article: XML element representing a PubmedArticle
            
        Returns:
            Complete abstract text with section labels preserved
        """
        # First, try to find English abstracts
        english_abstract = self._extract_abstract_by_language(article, 'eng')
        if english_abstract:
            return english_abstract
        
        # If no English abstract, try OtherAbstract elements
        other_english_abstract = self._extract_other_abstract_by_language(article, 'eng')
        if other_english_abstract:
            return other_english_abstract
        
        # Fallback to any available abstract
        fallback_abstract = self._extract_abstract_by_language(article, None)
        if fallback_abstract:
            return fallback_abstract
        
        # Last resort: try any OtherAbstract
        return self._extract_other_abstract_by_language(article, None)
    
    def _extract_abstract_by_language(self, article, language: Optional[str]) -> str:
        """
        Extract abstract from Abstract/AbstractText elements, optionally filtering by language.
        
        Args:
            article: XML element representing a PubmedArticle
            language: Language code to filter by (e.g., 'eng'), or None for any language
            
        Returns:
            Abstract text or empty string if not found
        """
        abstract_parts = []
        
        # Find all AbstractText elements
        abstract_texts = article.findall('.//Abstract/AbstractText')
        
        if not abstract_texts:
            return ""
        
        for abstract_text_elem in abstract_texts:
            # Check language if specified
            if language:
                elem_language = abstract_text_elem.get('Language', '')
                if elem_language != language:
                    continue
            
            # Get section label if present
            label = abstract_text_elem.get('Label', '')
            nlm_category = abstract_text_elem.get('NlmCategory', '')
            
            # Extract text content using itertext() to preserve nested tags
            text_content = ''.join(abstract_text_elem.itertext()).strip()
            
            if text_content:
                # Add section label if present
                if label:
                    abstract_parts.append(f"{label}: {text_content}")
                elif nlm_category:
                    abstract_parts.append(f"{nlm_category}: {text_content}")
                else:
                    abstract_parts.append(text_content)
        
        # Join all sections with double newlines for readability
        abstract_text = '\n\n'.join(abstract_parts) if abstract_parts else ""
        
        # Normalize text for consistent downstream processing
        return self._normalize_text(abstract_text)
    
    def _extract_pmcid_from_article(self, article) -> Optional[str]:
        """
        Extract PMCID from PubMed article XML.
        
        Args:
            article: XML element representing a PubmedArticle
            
        Returns:
            PMCID string (e.g., "PMC12345678") or None if not found
        """
        # Look for ArticleId elements with IdType="pmc"
        article_ids = article.findall('.//ArticleId')
        for article_id in article_ids:
            id_type = article_id.get('IdType', '').lower()
            if id_type == 'pmc':
                pmcid = article_id.text
                if pmcid and pmcid.startswith('PMC'):
                    return pmcid
        
        # Also check for ArticleIdList/ArticleId elements
        article_id_list = article.find('.//ArticleIdList')
        if article_id_list is not None:
            for article_id in article_id_list.findall('.//ArticleId'):
                id_type = article_id.get('IdType', '').lower()
                if id_type == 'pmc':
                    pmcid = article_id.text
                    if pmcid and pmcid.startswith('PMC'):
                        return pmcid
        
        return None
    
    
    def _extract_other_abstract_by_language(self, article, language: Optional[str]) -> str:
        """
        Extract abstract from OtherAbstract elements, optionally filtering by language.
        
        Args:
            article: XML element representing a PubmedArticle
            language: Language code to filter by (e.g., 'eng'), or None for any language
            
        Returns:
            Abstract text or empty string if not found
        """
        abstract_parts = []
        
        # Find all OtherAbstract elements
        other_abstracts = article.findall('.//OtherAbstract')
        
        if not other_abstracts:
            return ""
        
        for other_abstract in other_abstracts:
            # Check language if specified
            if language:
                elem_language = other_abstract.get('Language', '')
                if elem_language != language:
                    continue
            
            # Find AbstractText within this OtherAbstract
            abstract_texts = other_abstract.findall('.//AbstractText')
            
            for abstract_text_elem in abstract_texts:
                # Get section label if present
                label = abstract_text_elem.get('Label', '')
                nlm_category = abstract_text_elem.get('NlmCategory', '')
                
                # Extract text content using itertext() to preserve nested tags
                text_content = ''.join(abstract_text_elem.itertext()).strip()
                
                if text_content:
                    # Add section label if present
                    if label:
                        abstract_parts.append(f"{label}: {text_content}")
                    elif nlm_category:
                        abstract_parts.append(f"{nlm_category}: {text_content}")
                    else:
                        abstract_parts.append(text_content)
        
        # Join all sections with double newlines for readability
        abstract_text = '\n\n'.join(abstract_parts) if abstract_parts else ""
        
        # Normalize text for consistent downstream processing
        return self._normalize_text(abstract_text)
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for consistent downstream processing.
        
        Args:
            text: Raw text to normalize
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Normalize Unicode characters
        text = text.replace('\u2019', "'")  # Right single quotation mark
        text = text.replace('\u2018', "'")  # Left single quotation mark
        text = text.replace('\u201c', '"')  # Left double quotation mark
        text = text.replace('\u201d', '"')  # Right double quotation mark
        text = text.replace('\u2013', '-')  # En dash
        text = text.replace('\u2014', '-')  # Em dash
        text = text.replace('\u00a0', ' ')  # Non-breaking space
        
        # Remove any remaining control characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        return text.strip()
    
    def _parse_efetch_response(self, response_text: str, pmids: List[str], rettype: str) -> Dict[str, str]:
        """
        Parse EFetch response text to extract individual abstracts.
        
        Args:
            response_text: Raw response text
            pmids: List of PMIDs that were requested
            rettype: The return type that was requested
            
        Returns:
            Dictionary mapping PMID to abstract text
        """
        content_map = {}
        
        # Parse response based on rettype
        
        # Parse based on rettype
        if rettype == "medline":
            content_map = self._parse_medline_response(response_text, pmids)
        elif rettype == "abstract":
            # For abstract rettype, try to parse as best we can
            # This is less reliable than XML or MEDLINE
            content_map = self._parse_abstract_response(response_text, pmids)
        else:
            # For other rettypes, just return the raw text for single PMID
            if len(pmids) == 1:
                content_map[pmids[0]] = response_text.strip()
        
        # Return parsed results
        return content_map
    
    def _parse_medline_response(self, response_text: str, pmids: List[str]) -> Dict[str, str]:
        """
        Parse MEDLINE format response with proper continuation line handling.
        
        Args:
            response_text: Raw MEDLINE response text
            pmids: List of PMIDs that were requested
            
        Returns:
            Dictionary mapping PMID to abstract text
        """
        import re
        
        FIELD_RE = re.compile(r'^[A-Z]{2}\s{2}-\s')  # e.g., "AB  - "
        content_map = {}
        cur_pmid = None
        cur_field = None
        buf = []
        
        def flush():
            nonlocal buf
            if cur_pmid and cur_field == 'AB':
                prev = content_map.get(cur_pmid, '')
                chunk = ' '.join(x.strip() for x in buf).strip()
                if chunk:
                    content_map[cur_pmid] = (prev + ' ' + chunk).strip() if prev else chunk
            buf = []

        for raw in response_text.splitlines():
            line = raw.rstrip('\r')
            if line.startswith('PMID-'):
                flush()
                cur_pmid = line.split('PMID-')[1].strip()
                cur_field = None
                continue
            if FIELD_RE.match(line):
                flush()
                cur_field = line[:2]
                val = line[6:].strip()  # after "XX  - "
                buf = [val] if cur_field == 'AB' else []
            else:
                # continuation line (six spaces)
                if cur_field == 'AB' and line.startswith('      '):
                    buf.append(line.strip())
        
        flush()
        
        # Keep only requested PMIDs
        return {k: v for k, v in content_map.items() if k in set(pmids)}
    
    def _parse_retry_after(self, retry_after_header: str) -> int:
        """
        Parse Retry-After header value (seconds or HTTP-date).
        
        Args:
            retry_after_header: Retry-After header value
            
        Returns:
            Seconds to wait
        """
        from email.utils import parsedate_to_datetime
        from datetime import datetime
        
        try:
            return int(retry_after_header)
        except Exception:
            try:
                return max(0, int((parsedate_to_datetime(retry_after_header) - datetime.now(timezone.utc)).total_seconds()))
            except Exception:
                return 60
    
    def _parse_abstract_response(self, response_text: str, pmids: List[str]) -> Dict[str, str]:
        """
        Parse abstract format response (less reliable than MEDLINE/XML).
        
        Args:
            response_text: Raw abstract response text
            pmids: List of PMIDs that were requested
            
        Returns:
            Dictionary mapping PMID to abstract text
        """
        content_map = {}
        
        # Try different parsing strategies for abstract format
        parsed = False
        
        # Strategy 1: Look for PMID markers
        if 'PMID:' in response_text:
            parts = response_text.split('PMID:')
            for part in parts[1:]:  # Skip first empty part
                lines = part.strip().split('\n')
                if lines:
                    pmid = lines[0].strip()
                    if pmid in pmids:
                        # Look for abstract section
                        abstract_text = self._extract_abstract_from_lines(lines)
                        if abstract_text:
                            content_map[pmid] = abstract_text
                        else:
                            # Fallback: use all content after PMID
                            content_map[pmid] = '\n'.join(lines[1:]).strip()
            if content_map:
                parsed = True
        
        # Strategy 2: Single abstract fallback
        if not parsed:
            if len(pmids) == 1:
                content_map[pmids[0]] = response_text.strip()
                parsed = True
            else:
                logger.warning("Could not parse abstract response - no recognizable format found")
                logger.debug(f"Response contains: {response_text[:1000]}...")
        
        return content_map
    
    def _extract_abstract_from_lines(self, lines: List[str]) -> Optional[str]:
        """
        Extract abstract text from lines.
        
        Args:
            lines: Lines of text to search
            
        Returns:
            Abstract text or None if not found
        """
        # Look for abstract section markers
        abstract_markers = [
            'ABSTRACT:', 'Abstract:', 'abstract:',
            'SUMMARY:', 'Summary:', 'summary:',
            'BACKGROUND:', 'Background:', 'background:'
        ]
        
        abstract_start = -1
        
        # Find abstract start
        for i, line in enumerate(lines):
            line_lower = line.lower()
            for marker in abstract_markers:
                if marker.lower() in line_lower:
                    abstract_start = i
                    break
            if abstract_start >= 0:
                break
        
        if abstract_start < 0:
            # If no explicit abstract marker, look for content after title/author info
            # This is a heuristic - look for the first substantial paragraph
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                if (len(line_stripped) > 50 and  # Substantial line
                    not line_stripped.startswith('PMID') and
                    not line_stripped.startswith('doi:') and
                    not re.match(r'^[A-Z][a-z]+\([0-9]+\)', line_stripped)):  # Author format
                    abstract_start = i
                    break
        
        if abstract_start >= 0:
            # Extract from abstract start to end of entry
            abstract_text = '\n'.join(lines[abstract_start:]).strip()
            return abstract_text
        
        return None
    
    async def elink_pmid_to_pmcid(self, pmids: List[str]) -> Dict[str, Optional[str]]:
        """
        Convert PMIDs to PMCIDs using ELink.
        
        Args:
            pmids: List of PubMed IDs
            
        Returns:
            Dictionary mapping PMID to PMCID (None if not available)
        """
        if not pmids:
            return {}
            
        # Split into batches
        batches = [pmids[i:i + self.batch_size] for i in range(0, len(pmids), self.batch_size)]
        all_results = {}
        
        for batch in batches:
            params = self._get_base_params()
            params.update({
                'dbfrom': 'pubmed',
                'db': 'pmc',
                'id': ','.join(batch),
                'linkname': 'pubmed_pmc',
                'retmode': 'json'
            })
            
            logger.info(f"Converting {len(batch)} PMIDs to PMCIDs")
            result = await self._make_request(self.ELINK_URL, params)
            
            # Parse ELink response
            if 'linksets' in result:
                for linkset in result['linksets']:
                    pmid = str(linkset.get('ids', [''])[0])
                    pmcid = None
                    
                    if 'linksetdbs' in linkset:
                        for linksetdb in linkset['linksetdbs']:
                            if linksetdb.get('linkname') == 'pubmed_pmc':
                                links = linksetdb.get('links', [])
                                if links:
                                    link = links[0]
                                    # Handle both dict and string formats
                                    if isinstance(link, dict):
                                        pmcid = link.get('id')
                                    else:
                                        pmcid = str(link)
                                    
                                    # Ensure PMCID starts with PMC
                                    if pmcid and pmcid.startswith('PMC'):
                                        break
                    
                    all_results[pmid] = pmcid
        
        return all_results
    
    async def check_pmc_oa_status(self, pmcids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Check PMC open access status for a list of PMCIDs.
        
        Note: This method may not be reliable for all PMC articles.
        Consider using efetch with XML format for more accurate OA detection.
        
        Args:
            pmcids: List of PMC IDs
            
        Returns:
            Dictionary mapping PMCID to OA status information
        """
        if not pmcids:
            return {}
            
        # Split into batches
        batches = [pmcids[i:i + self.batch_size] for i in range(0, len(pmcids), self.batch_size)]
        all_results = {}
        
        for batch in batches:
            params = self._get_base_params()
            params.update({
                'db': 'pmc',
                'id': ','.join(batch),
                'retmode': 'json'
            })
            
            logger.info(f"Checking OA status for {len(batch)} PMCIDs")
            result = await self._make_request(self.ESUMMARY_URL, params)
            
            # Parse PMC summary response
            if 'result' in result:
                for pmcid, pmc_data in result['result'].items():
                    if pmcid != 'uids':  # Skip the uids field
                        # Handle articleids as a list of dicts
                        oa_route = 'unknown'
                        if 'articleids' in pmc_data:
                            for article_id in pmc_data['articleids']:
                                if isinstance(article_id, dict) and article_id.get('idtype') == 'oa_route':
                                    oa_route = article_id.get('value', 'unknown')
                                    break
                        
                        oa_info = {
                            'pmcid': pmcid,
                            'license': pmc_data.get('license', 'unknown'),
                            'oa_route': oa_route,
                            'is_oa': pmc_data.get('license', '').lower() in ['cc-by', 'cc-by-nc', 'cc-by-sa', 'cc-by-nd'],
                            'full_text_available': pmc_data.get('fulltext', 'N') == 'Y'
                        }
                        all_results[pmcid] = oa_info
        
        return all_results
    
    async def get_pmc_full_text(self, pmcid: str) -> Optional[str]:
        """
        Fetch full text content for a PMC ID (plain text version).
        
        Args:
            pmcid: PMC ID
            
        Returns:
            Full text content or None if not available
        """
        params = self._get_base_params()
        params.update({
            'db': 'pmc',
            'id': pmcid,
            'rettype': 'text',
            'retmode': 'text'
        })
        
        logger.info(f"Fetching full text (plain) for PMCID: {pmcid}", extra={
            "event": "pmc.fulltext.fetch.start",
            "message": f"Fetching full text (plain) for PMCID: {pmcid}",
            "pmcid": pmcid
        })
        try:
            result = await self._make_request(self.EFETCH_URL, params, expect_json=False)
            if isinstance(result, str):
                return result
            else:
                logger.warning(f"Unexpected full text response type: {type(result)}")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch full text for PMCID {pmcid}: {e}")
            return None

    async def get_pmc_full_text_jats(self, pmcid: str, include_refs: bool = True, include_captions: bool = True) -> Optional[str]:
        """
        Fetch full article text from PMC as JATS XML and convert to a comprehensive text string.
        Includes abstract, body, back matter (references), and captions depending on flags.
        
        Args:
            pmcid: PMC ID
            include_refs: Whether to include references
            include_captions: Whether to include figure/table captions
            
        Returns:
            Comprehensive full text content or None if not available
        """
        params = self._get_base_params()
        params.update({'db': 'pmc', 'id': pmcid, 'retmode': 'xml'})
        
        logger.info(f"Fetching full text (JATS XML) for PMCID: {pmcid}", extra={
            "event": "pmc.fulltext.fetch.start",
            "message": f"Fetching full text (JATS XML) for PMCID: {pmcid}",
            "pmcid": pmcid
        })
        try:
            xml_str = await self._make_request(self.EFETCH_URL, params, expect_json=False)
            if not isinstance(xml_str, str):
                logger.warning(f"Unexpected JATS response type for {pmcid}: {type(xml_str)}")
                return None

            # Parse XML
            from lxml import etree
            root = etree.fromstring(xml_str.encode("utf-8"))

            # Get namespace - handle both default and prefixed namespaces
            default_ns = root.nsmap.get(None) or root.nsmap.get('')
            if default_ns:
                # Use a proper prefix for the default namespace
                ns = {'ns': default_ns}
            else:
                # No namespace, use local-name() function
                ns = {}

            # Extract sections
            chunks = []

            # Title & metadata
            if ns:
                for node in root.xpath('.//ns:article-title', namespaces=ns):
                    chunks.append(' '.join(node.itertext()))
            else:
                for node in root.xpath('.//*[local-name()="article-title"]'):
                    chunks.append(' '.join(node.itertext()))

            # Abstract(s)
            if ns:
                for node in root.xpath('.//ns:abstract', namespaces=ns):
                    chunks.append(' '.join(node.itertext()))
            else:
                for node in root.xpath('.//*[local-name()="abstract"]'):
                    chunks.append(' '.join(node.itertext()))

            # Main body
            if ns:
                for node in root.xpath('.//ns:body', namespaces=ns):
                    chunks.append(' '.join(node.itertext()))
            else:
                for node in root.xpath('.//*[local-name()="body"]'):
                    chunks.append(' '.join(node.itertext()))

            # Captions (figures/tables)
            if include_captions:
                if ns:
                    for node in root.xpath('.//ns:fig/ns:caption|.//ns:table-wrap/ns:caption', namespaces=ns):
                        chunks.append(' '.join(node.itertext()))
                else:
                    for node in root.xpath('.//*[local-name()="fig"]/*[local-name()="caption"]|.//*[local-name()="table-wrap"]/*[local-name()="caption"]'):
                        chunks.append(' '.join(node.itertext()))

            # Footnotes / acknowledgments
            if ns:
                for node in root.xpath('.//ns:fn-group|.//ns:ack', namespaces=ns):
                    chunks.append(' '.join(node.itertext()))
            else:
                for node in root.xpath('.//*[local-name()="fn-group"]|.//*[local-name()="ack"]'):
                    chunks.append(' '.join(node.itertext()))

            # References
            if include_refs:
                if ns:
                    for node in root.xpath('.//ns:ref-list', namespaces=ns):
                        chunks.append(' '.join(node.itertext()))
                else:
                    for node in root.xpath('.//*[local-name()="ref-list"]'):
                        chunks.append(' '.join(node.itertext()))

            # Normalize whitespace and HTML entities
            text = self._normalize_text(' '.join(chunks))
            logger.info(f"JATS extraction completed for {pmcid}: {len(text)} characters", extra={
                "event": "pmc.fulltext.fetch.done",
                "message": f"JATS extraction completed for {pmcid}: {len(text)} characters",
                "pmcid": pmcid,
                "character_count": len(text)
            })
            return text or None

        except Exception as e:
            logger.error(f"Failed to fetch/parse JATS for {pmcid}: {e}")
            return None

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text by unescaping HTML entities and collapsing whitespace.
        
        Args:
            text: Raw text to normalize
            
        Returns:
            Normalized text
        """
        import html
        # Unescape HTML entities
        text = html.unescape(text)
        # Collapse whitespace
        return ' '.join(text.split())
    
    def calculate_query_hash(self, query: str) -> str:
        """
        Calculate hash for query caching.
        
        Args:
            query: Search query string
            
        Returns:
            SHA256 hash of normalized query
        """
        # Normalize query for consistent hashing
        normalized = re.sub(r'\s+', ' ', query.lower().strip())
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    async def health_check(self) -> bool:
        """
        Perform health check on PubMed APIs.
        
        Returns:
            True if all APIs are healthy
        """
        try:
            # Test ESearch with a simple query
            result = await self.esearch("cancer", max_results=1)
            # Check if we got a valid count
            count = result.get('count', '0')
            return bool(int(count) >= 0)
        except Exception as e:
            logger.exception("PubMed health check failed")
            return False
    
    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Get current rate limiting information.
        
        Returns:
            Dictionary with rate limit details
        """
        return {
            'rate_limit_per_sec': self.rate_limit_per_sec,
            'min_delay': self.min_delay,
            'consecutive_failures': self.consecutive_failures,
            'circuit_breaker_open': self.circuit_breaker_open,
            'circuit_breaker_open_until': self.circuit_breaker_open_until.isoformat() if self.circuit_breaker_open_until else None,
            'esearch_calls': self.esearch_calls,
            'efetch_calls': self.efetch_calls,
            'esummary_calls': self.esummary_calls
        }


class PubMedBatchProcessor:
    """Helper class for processing large batches of PubMed operations."""
    
    def __init__(self, client: PubMedClient, max_concurrent: int = 5):
        """
        Initialize batch processor.
        
        Args:
            client: PubMed client instance
            max_concurrent: Maximum concurrent operations
        """
        self.client = client
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_pmids_in_batches(
        self, 
        pmids: List[str], 
        operation: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Process PMIDs in batches with controlled concurrency.
        
        Args:
            pmids: List of PMIDs to process
            operation: Operation to perform (esummary, efetch, elink)
            **kwargs: Additional arguments for the operation
            
        Returns:
            Combined results from all batches
        """
        if not pmids:
            return {}
        
        # Split into batches
        batches = [pmids[i:i + self.client.batch_size] for i in range(0, len(pmids), self.client.batch_size)]
        
        async def process_batch(batch: List[str]) -> Dict[str, Any]:
            async with self.semaphore:
                if operation == 'esummary':
                    return await self.client.esummary_batch(batch)
                elif operation == 'efetch':
                    return await self.client.efetch_batch(batch, **kwargs)
                elif operation == 'efetch_xml':
                    return await self.client.efetch_abstracts_xml(batch)
                elif operation == 'elink':
                    return await self.client.elink_pmid_to_pmcid(batch)
                else:
                    raise ValueError(f"Unknown operation: {operation}")
        
        # Process all batches concurrently
        tasks = [process_batch(batch) for batch in batches]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results and handle errors
        combined_results = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch {i} failed: {result}")
                continue
            combined_results.update(result)
        
        return combined_results
