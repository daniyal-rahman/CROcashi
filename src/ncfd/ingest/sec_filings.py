"""
Robust SEC filings ingestion client for CROcashi.

This module handles SEC document ingestion with:
- Rate limiting and polite scraping
- Robust HTML/TXT parsing with fallbacks
- Content hashing and idempotent storage
- Section extraction with multiple strategies
- Integration with LangExtract for narrative parsing
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Generator
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import html2text

from .sec_types import (
    FilingMetadata, FilingDocument, EightKItem, TenKSection,
    DocumentSection, ContentHash, ExtractionResult
)

logger = logging.getLogger(__name__)


class SecFilingsClient:
    """
    Robust SEC filings client with rate limiting, caching, and fallback parsing.
    
    Addresses key challenges:
    - Rate limiting and blocking prevention
    - Structural inconsistency handling
    - Content drift tracking
    - Fallback parsing strategies
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize SEC filings client.
        
        Args:
            config: Configuration dictionary with API settings
        """
        self.config = config
        self.base_url = "https://www.sec.gov/Archives/edgar/data"
        self.session = self._create_session()
        self.rate_limiter = RateLimiter(
            requests_per_minute=config.get('rate_limit_per_minute', 2),
            burst_size=config.get('burst_size', 5)
        )
        self.cache_dir = Path(config.get('cache_dir', '.cache/sec'))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Parsing configuration
        self.html_parser = html2text.HTML2Text()
        self.html_parser.ignore_links = False
        self.html_parser.ignore_images = True
        self.html_parser.body_width = 0  # No line wrapping
        
        # Section detection patterns
        self.section_patterns = self._build_section_patterns()
        
    def _create_session(self) -> requests.Session:
        """Create session with proper headers and user agent."""
        session = requests.Session()
        
        # Set proper headers to avoid blocking
        session.headers.update({
            'User-Agent': self.config.get('user_agent', 'CROcashi/1.0 (clinical-trial-analysis@example.com)'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        return session
    
    def _build_section_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Build robust section detection patterns with fallbacks."""
        patterns = {
            '8k_items': [
                # Primary patterns
                re.compile(r'(?i)\bItem\s+(\d+\.\d+)\b.*?(?=\bItem\s+\d+\.\d+\b|SIGNATURES|EXHIBITS|\Z)', re.DOTALL),
                re.compile(r'(?i)\bItem\s+(\d+\.\d+)\b.*?(?=\n\s*\n|\Z)', re.DOTALL),
                # Fallback patterns
                re.compile(r'(?i)\bItem\s+(\d+\.\d+)\b.*?(?=\bItem\b|\Z)', re.DOTALL),
            ],
            '10k_sections': [
                # Business sections
                re.compile(r'(?i)\b(?:Item\s+)?1A?\s*[\.:]\s*Risk\s+Factors?\b.*?(?=\b(?:Item\s+)?1B?\b|\Z)', re.DOTALL),
                re.compile(r'(?i)\b(?:Item\s+)?1\s*[\.:]\s*Business\b.*?(?=\b(?:Item\s+)?1A?\b|\Z)', re.DOTALL),
                # Clinical development
                re.compile(r'(?i)\b(?:Item\s+)?1\s*[\.:]\s*Business.*?Clinical\s+Development.*?(?=\b(?:Item\s+)?2\b|\Z)', re.DOTALL),
                # Fallback patterns
                re.compile(r'(?i)\bRisk\s+Factors?\b.*?(?=\b(?:Item\s+)?\d+\b|\Z)', re.DOTALL),
            ],
            'general_sections': [
                # Generic item patterns
                re.compile(r'(?i)\b(?:Item\s+)?(\d+[A-Z]?)\s*[\.:]\s*([^.\n]+?)\b.*?(?=\b(?:Item\s+)?\d+[A-Z]?\b|\Z)', re.DOTALL),
            ]
        }
        return patterns
    
    def fetch_company_filings(
        self, 
        cik: int, 
        form_types: List[str], 
        since_date: date,
        max_filings: int = 100
    ) -> List[FilingMetadata]:
        """
        Fetch filing metadata for a company with rate limiting.
        
        Args:
            cik: Company CIK number
            form_types: List of form types to fetch (e.g., ['8-K', '10-K', '10-Q'])
            since_date: Only fetch filings since this date
            max_filings: Maximum number of filings to fetch
            
        Returns:
            List of filing metadata
        """
        filings = []
        
        for form_type in form_types:
            try:
                form_filings = self._fetch_form_filings(cik, form_type, since_date, max_filings)
                filings.extend(form_filings)
                
                # Rate limiting between form types
                self.rate_limiter.wait_if_needed()
                
            except Exception as e:
                logger.error(f"Error fetching {form_type} filings for CIK {cik}: {e}")
                continue
        
        # Sort by filing date, newest first
        filings.sort(key=lambda x: x.filing_date, reverse=True)
        
        return filings[:max_filings]
    
    def _fetch_form_filings(
        self, 
        cik: int, 
        form_type: str, 
        since_date: date,
        max_filings: int
    ) -> List[FilingMetadata]:
        """Fetch filings for a specific form type."""
        # Build the filing index URL
        cik_str = str(cik).zfill(10)
        index_url = f"{self.base_url}/{cik_str}/index.json"
        
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            response = self.session.get(index_url, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            directory = data.get('directory', {})
            filings = directory.get('item', [])
            
            # Filter by form type and date
            filtered_filings = []
            for filing in filings:
                if filing.get('type') == form_type:
                    filing_date = self._parse_filing_date(filing.get('lastModified', ''))
                    if filing_date and filing_date >= since_date:
                        metadata = FilingMetadata(
                            cik=cik,
                            accession=filing.get('name'),
                            form_type=form_type,
                            filing_date=filing_date,
                            company_name=filing.get('companyName', ''),
                            description=filing.get('description', ''),
                            url=urljoin(index_url, filing.get('name', ''))
                        )
                        filtered_filings.append(metadata)
                        
                        if len(filtered_filings) >= max_filings:
                            break
            
            return filtered_filings
            
        except Exception as e:
            logger.error(f"Error fetching {form_type} index for CIK {cik}: {e}")
            return []
    
    def fetch_filing_document(self, metadata: FilingMetadata) -> Optional[FilingDocument]:
        """
        Fetch and parse filing document with caching and fallback parsing.
        
        Args:
            metadata: Filing metadata
            
        Returns:
            Parsed filing document or None if failed
        """
        # Check cache first
        cache_key = f"{metadata.cik}_{metadata.accession}"
        cached_doc = self._get_cached_document(cache_key)
        if cached_doc:
            logger.info(f"Using cached document for {cache_key}")
            return cached_doc
        
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            # Fetch the document
            response = self.session.get(metadata.url, timeout=60)
            response.raise_for_status()
            
            content = response.text
            content_hash = self._compute_content_hash(content)
            
            # Parse document with fallback strategies
            sections = self._extract_sections(content, metadata.form_type)
            
            # Create document object
            document = FilingDocument(
                metadata=metadata,
                content=content,
                content_hash=content_hash,
                sections=sections,
                extracted_at=datetime.utcnow()
            )
            
            # Cache the document
            self._cache_document(cache_key, document)
            
            return document
            
        except Exception as e:
            logger.error(f"Error fetching document for {metadata.accession}: {e}")
            return None
    
    def _extract_sections(self, content: str, form_type: str) -> List[DocumentSection]:
        """
        Extract document sections using multiple strategies.
        
        Args:
            content: Document content
            form_type: SEC form type
            
        Returns:
            List of extracted sections
        """
        sections = []
        
        # Strategy 1: HTML outline parsing (most reliable)
        html_sections = self._extract_html_sections(content)
        if html_sections:
            sections.extend(html_sections)
            logger.info(f"Extracted {len(html_sections)} sections using HTML outline")
        
        # Strategy 2: Pattern-based extraction (fallback)
        if not sections or len(sections) < 2:
            pattern_sections = self._extract_pattern_sections(content, form_type)
            if pattern_sections:
                sections.extend(pattern_sections)
                logger.info(f"Extracted {len(pattern_sections)} sections using patterns")
        
        # Strategy 3: Manual section detection (last resort)
        if not sections:
            manual_sections = self._extract_manual_sections(content, form_type)
            if manual_sections:
                sections.extend(manual_sections)
                logger.info(f"Extracted {len(manual_sections)} sections manually")
        
        # Normalize and deduplicate sections
        sections = self._normalize_sections(sections)
        
        return sections
    
    def _extract_html_sections(self, content: str) -> List[DocumentSection]:
        """Extract sections using HTML heading structure."""
        sections = []
        
        try:
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find all headings (h1-h6)
            headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            
            for i, heading in enumerate(headings):
                heading_text = heading.get_text(strip=True)
                if not heading_text:
                    continue
                
                # Get content until next heading
                section_content = ""
                current = heading.next_sibling
                while current and current.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    if hasattr(current, 'get_text'):
                        section_content += current.get_text()
                    current = current.next_sibling
                
                if section_content.strip():
                    section = DocumentSection(
                        title=heading_text,
                        content=section_content.strip(),
                        content_hash=self._compute_content_hash(section_content),
                        start_offset=0,  # Approximate
                        end_offset=len(section_content),
                        confidence="HIGH"
                    )
                    sections.append(section)
                    
        except Exception as e:
            logger.warning(f"HTML parsing failed: {e}")
        
        return sections
    
    def _extract_pattern_sections(self, content: str, form_type: str) -> List[DocumentSection]:
        """Extract sections using regex patterns."""
        sections = []
        
        # Choose appropriate patterns
        if form_type == '8-K':
            patterns = self.section_patterns['8k_items']
        elif form_type in ['10-K', '10-Q']:
            patterns = self.section_patterns['10k_sections']
        else:
            patterns = self.section_patterns['general_sections']
        
        for pattern in patterns:
            matches = pattern.finditer(content)
            for match in matches:
                if form_type == '8-K':
                    item_number = match.group(1)
                    section_content = match.group(0)
                    title = f"Item {item_number}"
                else:
                    title = match.group(2) if len(match.groups()) > 1 else "Unknown Section"
                    section_content = match.group(0)
                
                if section_content.strip():
                    section = DocumentSection(
                        title=title,
                        content=section_content.strip(),
                        content_hash=self._compute_content_hash(section_content),
                        start_offset=match.start(),
                        end_offset=match.end(),
                        confidence="MEDIUM"
                    )
                    sections.append(section)
        
        return sections
    
    def _extract_manual_sections(self, content: str, form_type: str) -> List[DocumentSection]:
        """Manual section extraction as last resort."""
        sections = []
        
        # Split by common delimiters
        delimiters = [
            '\n\n\n',  # Triple newlines
            '\r\n\r\n\r\n',  # Windows triple newlines
            'SIGNATURES',
            'EXHIBITS',
            'PART I',
            'PART II',
            'ITEM',
        ]
        
        # Find the best delimiter
        best_delimiter = None
        max_splits = 0
        
        for delimiter in delimiters:
            splits = content.split(delimiter)
            if len(splits) > max_splits and len(splits) > 1:
                max_splits = len(splits)
                best_delimiter = delimiter
        
        if best_delimiter:
            parts = content.split(best_delimiter)
            for i, part in enumerate(parts):
                if part.strip():
                    section = DocumentSection(
                        title=f"Section {i+1}",
                        content=part.strip(),
                        content_hash=self._compute_content_hash(part),
                        start_offset=0,  # Approximate
                        end_offset=len(part),
                        confidence="LOW"
                    )
                    sections.append(section)
        
        return sections
    
    def _normalize_sections(self, sections: List[DocumentSection]) -> List[DocumentSection]:
        """Normalize and deduplicate sections."""
        # Remove empty sections
        sections = [s for s in sections if s.content.strip()]
        
        # Deduplicate by content hash
        seen_hashes = set()
        unique_sections = []
        
        for section in sections:
            if section.content_hash not in seen_hashes:
                seen_hashes.add(section.content_hash)
                unique_sections.append(section)
        
        # Sort by confidence (HIGH > MEDIUM > LOW)
        confidence_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        unique_sections.sort(key=lambda x: confidence_order.get(x.confidence, 0), reverse=True)
        
        return unique_sections
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _parse_filing_date(self, date_str: str) -> Optional[date]:
        """Parse filing date string."""
        if not date_str:
            return None
        
        # Try multiple date formats
        date_formats = [
            '%Y-%m-%d',
            '%Y%m%d',
            '%m/%d/%Y',
            '%d/%m/%Y'
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _get_cached_document(self, cache_key: str) -> Optional[FilingDocument]:
        """Get document from cache if available and fresh."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            # Check if cache is fresh (24 hours)
            if time.time() - cache_file.stat().st_mtime > 86400:
                return None
            
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
            
            # Reconstruct document object
            return FilingDocument.from_dict(cached_data)
            
        except Exception as e:
            logger.warning(f"Cache read failed for {cache_key}: {e}")
            return None
    
    def _cache_document(self, cache_key: str, document: FilingDocument):
        """Cache document to disk."""
        try:
            cache_file = self.cache_dir / f"{cache_key}.json"
            
            # Convert to dict for JSON serialization
            doc_dict = document.to_dict()
            
            with open(cache_file, 'w') as f:
                json.dump(doc_dict, f, indent=2, default=str)
                
        except Exception as e:
            logger.warning(f"Cache write failed for {cache_key}: {e}")


class RateLimiter:
    """Rate limiter for SEC API requests."""
    
    def __init__(self, requests_per_minute: int = 2, burst_size: int = 5):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_refill = time.time()
        self.refill_rate = requests_per_minute / 60.0  # tokens per second
    
    def wait_if_needed(self):
        """Wait if rate limit is exceeded."""
        now = time.time()
        
        # Refill tokens
        time_passed = now - self.last_refill
        tokens_to_add = time_passed * self.refill_rate
        self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
        self.last_refill = now
        
        # If no tokens available, wait
        if self.tokens < 1:
            wait_time = (1 - self.tokens) / self.refill_rate
            logger.info(f"Rate limited, waiting {wait_time:.2f}s")
            time.sleep(wait_time)
            self.tokens = 0
            self.last_refill = time.time()
        else:
            self.tokens -= 1
