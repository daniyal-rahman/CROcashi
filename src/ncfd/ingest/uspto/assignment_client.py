"""
USPTO Assignment API Client

Client for fetching US patent assignment data from USPTO assignment database.
Handles assignment records, ownership changes, and consideration details.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional, Any, Iterator
from decimal import Decimal
import requests
from bs4 import BeautifulSoup

from .patent_types import AssignmentRecord, USPTO_ASSIGNMENT_BASE
from .patent_client import RateLimiter

logger = logging.getLogger(__name__)


class USPTOAssignmentClient:
    """
    Client for USPTO assignment data with parsing and caching.
    
    Features:
    - Assignment record retrieval by patent number
    - Assignment record retrieval by assignee name
    - Parsing of assignment details and consideration
    - Caching for performance
    - Rate limiting
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize USPTO assignment client.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        
        # API configuration
        self.assignment_base = self.config.get("assignment_base", USPTO_ASSIGNMENT_BASE)
        self.timeout = self.config.get("timeout_seconds", 60)
        
        # Rate limiting
        rpm = self.config.get("rate_limit_rpm", 60)  # More conservative for assignment API
        self.rate_limiter = RateLimiter(rpm)
        
        # Caching
        cache_dir = self.config.get("cache_dir", "data/uspto_cache/assignments")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl_days = self.config.get("cache_ttl_days", 30)
        
        # HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CROcashi-Assignment-Client/1.0 (Research Use)'
        })
        
        logger.info(f"Initialized USPTO assignment client with cache dir: {self.cache_dir}")
    
    def fetch_assignments_for_patent(self, patent_number: str) -> List[AssignmentRecord]:
        """
        Fetch all assignment records for a specific patent.
        
        Args:
            patent_number: US patent number
            
        Returns:
            List of assignment records for the patent
        """
        logger.debug(f"Fetching assignments for patent: {patent_number}")
        
        # Check cache first
        cache_key = f"patent_{patent_number}"
        cached_assignments = self._get_cached_assignments(cache_key)
        if cached_assignments:
            return cached_assignments
        
        try:
            # Normalize patent number
            normalized_number = self._normalize_patent_number(patent_number)
            
            # Fetch assignment data
            assignments = self._fetch_patent_assignments(normalized_number)
            
            # Cache results
            self._cache_assignments(cache_key, assignments)
            
            logger.info(f"Found {len(assignments)} assignments for patent {patent_number}")
            return assignments
            
        except Exception as e:
            logger.error(f"Error fetching assignments for patent {patent_number}: {e}")
            return []
    
    def fetch_assignments_for_assignee(self, assignee_name: str,
                                     since_date: Optional[date] = None,
                                     max_assignments: int = 1000) -> List[AssignmentRecord]:
        """
        Fetch assignment records for a specific assignee.
        
        Args:
            assignee_name: Name of assignee
            since_date: Only return assignments since this date
            max_assignments: Maximum number of assignments to return
            
        Returns:
            List of assignment records for the assignee
        """
        logger.info(f"Fetching assignments for assignee: {assignee_name}")
        
        # Check cache first
        cache_key = f"assignee_{assignee_name}_{since_date or 'all'}"
        cached_assignments = self._get_cached_assignments(cache_key)
        if cached_assignments:
            return cached_assignments[:max_assignments]
        
        try:
            # Fetch assignment data
            assignments = self._fetch_assignee_assignments(assignee_name, since_date, max_assignments)
            
            # Cache results
            self._cache_assignments(cache_key, assignments)
            
            logger.info(f"Found {len(assignments)} assignments for assignee {assignee_name}")
            return assignments
            
        except Exception as e:
            logger.error(f"Error fetching assignments for assignee {assignee_name}: {e}")
            return []
    
    def _fetch_patent_assignments(self, patent_number: str) -> List[AssignmentRecord]:
        """Fetch assignments for a specific patent number."""
        assignments = []
        
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            # Build search URL
            search_url = f"{self.assignment_base}/patent/index.html"
            
            # Perform search
            search_params = {
                'searchText': patent_number,
                'searchType': 'patent'
            }
            
            response = self.session.get(search_url, params=search_params, timeout=self.timeout)
            response.raise_for_status()
            
            # Parse search results
            assignments = self._parse_assignment_search_results(response.text, patent_number)
            
        except Exception as e:
            logger.error(f"Error fetching patent assignments for {patent_number}: {e}")
        
        return assignments
    
    def _fetch_assignee_assignments(self, assignee_name: str, 
                                  since_date: Optional[date],
                                  max_assignments: int) -> List[AssignmentRecord]:
        """Fetch assignments for a specific assignee."""
        assignments = []
        
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            # Build search URL
            search_url = f"{self.assignment_base}/patent/index.html"
            
            # Perform search
            search_params = {
                'searchText': assignee_name,
                'searchType': 'assignee'
            }
            
            response = self.session.get(search_url, params=search_params, timeout=self.timeout)
            response.raise_for_status()
            
            # Parse search results
            all_assignments = self._parse_assignment_search_results(response.text, assignee_name)
            
            # Filter by date if specified
            if since_date:
                assignments = [a for a in all_assignments 
                             if a.recorded_date and a.recorded_date >= since_date]
            else:
                assignments = all_assignments
            
            # Limit results
            assignments = assignments[:max_assignments]
            
        except Exception as e:
            logger.error(f"Error fetching assignee assignments for {assignee_name}: {e}")
        
        return assignments
    
    def _parse_assignment_search_results(self, html_content: str, search_term: str) -> List[AssignmentRecord]:
        """Parse assignment search results from HTML."""
        assignments = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find assignment records in the results
            # This is a simplified parser - actual USPTO HTML structure may vary
            assignment_rows = soup.find_all('tr', class_='assignment-row')
            
            for row in assignment_rows:
                try:
                    assignment = self._parse_assignment_row(row)
                    if assignment:
                        assignments.append(assignment)
                except Exception as e:
                    logger.warning(f"Failed to parse assignment row: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing assignment search results: {e}")
        
        return assignments
    
    def _parse_assignment_row(self, row_element) -> Optional[AssignmentRecord]:
        """Parse a single assignment row from search results."""
        try:
            # Extract basic information
            cells = row_element.find_all('td')
            if len(cells) < 6:
                return None
            
            # Extract assignment details
            reel_frame = self._extract_text(cells[0])
            assignment_id = self._extract_assignment_id(reel_frame)
            assignor = self._extract_text(cells[1])
            assignee = self._extract_text(cells[2])
            execution_date = self._parse_date(self._extract_text(cells[3]))
            recorded_date = self._parse_date(self._extract_text(cells[4]))
            patent_numbers = self._extract_patent_numbers(self._extract_text(cells[5]))
            
            # Get assignment details if available
            assignment_text, assignment_type, consideration = self._extract_assignment_details(assignment_id)
            
            return AssignmentRecord(
                assignment_id=assignment_id,
                reel_frame=reel_frame,
                patent_numbers=patent_numbers,
                assignor=assignor,
                assignee=assignee,
                assignment_type=assignment_type or "assignment",
                execution_date=execution_date,
                recorded_date=recorded_date,
                assignment_text=assignment_text,
                consideration_amount=consideration.get('amount') if consideration else None,
                consideration_type=consideration.get('type') if consideration else None,
                source_url=f"{self.assignment_base}/patent/index.html#{assignment_id}",
                extracted_at=datetime.now(UTC)
            )
            
        except Exception as e:
            logger.warning(f"Error parsing assignment row: {e}")
            return None
    
    def _extract_assignment_details(self, assignment_id: str) -> tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
        """Extract detailed assignment information."""
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            # Fetch assignment detail page
            detail_url = f"{self.assignment_base}/patent/index.html#/patent/search/resultAssignment?id={assignment_id}"
            response = self.session.get(detail_url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract assignment text
            assignment_text = None
            text_element = soup.find('div', class_='assignment-text')
            if text_element:
                assignment_text = text_element.get_text(strip=True)
            
            # Determine assignment type
            assignment_type = self._determine_assignment_type(assignment_text or "")
            
            # Extract consideration information
            consideration = self._extract_consideration(assignment_text or "")
            
            return assignment_text, assignment_type, consideration
            
        except Exception as e:
            logger.warning(f"Error extracting assignment details for {assignment_id}: {e}")
            return None, None, None
    
    def _determine_assignment_type(self, assignment_text: str) -> str:
        """Determine assignment type from assignment text."""
        text_lower = assignment_text.lower()
        
        if any(term in text_lower for term in ['license', 'licensing']):
            return "license"
        elif any(term in text_lower for term in ['security', 'collateral']):
            return "security_agreement"
        elif any(term in text_lower for term in ['merger', 'acquisition']):
            return "merger"
        elif any(term in text_lower for term in ['court', 'judgment']):
            return "court_order"
        else:
            return "assignment"
    
    def _extract_consideration(self, assignment_text: str) -> Optional[Dict[str, Any]]:
        """Extract consideration details from assignment text."""
        if not assignment_text:
            return None
        
        consideration = {}
        
        # Look for monetary amounts
        money_patterns = [
            r'\$[\d,]+(?:\.\d{2})?',
            r'(\d+(?:,\d{3})*(?:\.\d{2})?) dollars',
            r'sum of (\d+(?:,\d{3})*(?:\.\d{2})?)',
        ]
        
        for pattern in money_patterns:
            matches = re.findall(pattern, assignment_text, re.IGNORECASE)
            if matches:
                try:
                    # Extract numeric value
                    amount_str = matches[0].replace(',', '').replace('$', '')
                    amount = Decimal(amount_str)
                    consideration['amount'] = amount
                    consideration['type'] = 'monetary'
                    break
                except:
                    continue
        
        # Look for other consideration types
        if 'equity' in assignment_text.lower() or 'shares' in assignment_text.lower():
            consideration['type'] = 'equity'
        elif 'license' in assignment_text.lower():
            consideration['type'] = 'licensing'
        elif not consideration:
            consideration['type'] = 'other'
        
        return consideration if consideration else None
    
    def _extract_text(self, element) -> str:
        """Safely extract text from HTML element."""
        if element:
            return element.get_text(strip=True)
        return ""
    
    def _extract_assignment_id(self, reel_frame: str) -> str:
        """Extract assignment ID from reel/frame number."""
        # Assignment ID is typically the reel/frame number
        return reel_frame.replace('/', '_').replace(' ', '_')
    
    def _extract_patent_numbers(self, patent_text: str) -> List[str]:
        """Extract patent numbers from text."""
        # Look for patent numbers in various formats
        patterns = [
            r'US\d{7,8}[A-Z]?\d?',
            r'\d{7,8}',
        ]
        
        patent_numbers = []
        for pattern in patterns:
            matches = re.findall(pattern, patent_text)
            patent_numbers.extend(matches)
        
        # Clean and deduplicate
        clean_numbers = []
        for num in patent_numbers:
            if not num.startswith('US'):
                num = f'US{num}'
            if num not in clean_numbers:
                clean_numbers.append(num)
        
        return clean_numbers
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string into date object."""
        if not date_str:
            return None
        
        # Common date formats in USPTO data
        formats = [
            '%m/%d/%Y',
            '%Y-%m-%d',
            '%m-%d-%Y',
            '%d/%m/%Y',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except:
                continue
        
        logger.warning(f"Could not parse date: {date_str}")
        return None
    
    def _normalize_patent_number(self, patent_number: str) -> str:
        """Normalize patent number for API queries."""
        # Remove common prefixes and format consistently
        number = patent_number.replace('US', '').replace('us', '')
        number = number.replace(',', '').replace(' ', '')
        return number
    
    def _get_cached_assignments(self, cache_key: str) -> Optional[List[AssignmentRecord]]:
        """Get cached assignment records."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not self._is_cache_valid(cache_file):
            return None
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                return [AssignmentRecord(**item) for item in data]
        except Exception as e:
            logger.warning(f"Failed to load cached assignments {cache_key}: {e}")
            return None
    
    def _cache_assignments(self, cache_key: str, assignments: List[AssignmentRecord]):
        """Cache assignment records."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            data = [assignment.__dict__ for assignment in assignments]
            with open(cache_file, 'w') as f:
                json.dump(data, f, default=str, indent=2)
        except Exception as e:
            logger.warning(f"Failed to cache assignments {cache_key}: {e}")
    
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
