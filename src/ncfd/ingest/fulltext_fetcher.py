#!/usr/bin/env python3
"""
Full Text Fetcher Service for Checkpoint 4

This service handles fetching full text from open-access sources,
with TTL management and proper error handling.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
import requests
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

class FullTextFetcher:
    """Service for fetching full text from open-access sources."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the full text fetcher.
        
        Args:
            config: Configuration dictionary with settings
        """
        self.config = config or {}
        
        # Default TTL: 90 days
        self.default_ttl_days = self.config.get('default_ttl_days', 90)
        
        # User agent for requests
        self.user_agent = self.config.get('user_agent', 'NCFD-FullTextFetcher/1.0')
        
        # Timeout for requests
        self.timeout = self.config.get('timeout', 30)
        
        # Maximum text size (to prevent huge documents)
        self.max_text_size = self.config.get('max_text_size', 1024 * 1024)  # 1MB
        
        # Known OA sources and their text extraction patterns
        self.oa_sources = {
            'biorxiv': {
                'base_url': 'https://www.biorxiv.org',
                'text_pattern': r'<div class="highwire-cite-title">(.*?)</div>',
                'is_oa': True
            },
            'medrxiv': {
                'base_url': 'https://www.medrxiv.org',
                'text_pattern': r'<div class="highwire-cite-title">(.*?)</div>',
                'is_oa': True
            },
            'arxiv': {
                'base_url': 'https://arxiv.org',
                'text_pattern': r'<div class="title">(.*?)</div>',
                'is_oa': True
            },
            'pmc': {
                'base_url': 'https://www.ncbi.nlm.nih.gov/pmc',
                'text_pattern': r'<div class="tsec">(.*?)</div>',
                'is_oa': True
            }
        }
        
        logger.info(f"Full text fetcher initialized with TTL: {self.default_ttl_days} days")
    
    def can_fetch_fulltext(self, document: Dict[str, Any]) -> bool:
        """
        Check if full text can be fetched for a document.
        
        Args:
            document: Document metadata
            
        Returns:
            True if full text can be fetched
        """
        # Check if document is open access
        if not document.get('is_open_access', False):
            logger.info(f"Document {document.get('doc_id')} is not open access - cannot fetch full text")
            return False
        
        # Check if document has a URL
        if not document.get('source_url'):
            logger.info(f"Document {document.get('doc_id')} has no source URL - cannot fetch full text")
            return False
        
        # Check if URL is from a known OA source
        url = document.get('source_url', '')
        for source_name, source_info in self.oa_sources.items():
            if source_name in url.lower():
                return True
        
        # Check for common OA indicators in URL
        oa_indicators = ['openaccess', 'oa', 'free', 'public', 'creativecommons']
        if any(indicator in url.lower() for indicator in oa_indicators):
            return True
        
        logger.info(f"Document {document.get('doc_id')} source not recognized as OA - cannot fetch full text")
        return False
    
    def fetch_fulltext(self, document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Fetch full text for a document.
        
        Args:
            document: Document metadata
            
        Returns:
            Dictionary with full text data or None if failed
        """
        doc_id = document.get('doc_id')
        source_url = document.get('source_url')
        
        if not self.can_fetch_fulltext(document):
            return None
        
        try:
            logger.info(f"Fetching full text for document {doc_id} from {source_url}")
            
            # Make request to source URL
            headers = {'User-Agent': self.user_agent}
            response = requests.get(source_url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Extract text content
            text_content = self._extract_text_from_html(response.text)
            
            if not text_content:
                logger.warning(f"Could not extract text content from {source_url}")
                return None
            
            # Check text size
            if len(text_content) > self.max_text_size:
                logger.warning(f"Text content too large ({len(text_content)} chars) for document {doc_id}")
                return None
            
            # Calculate TTL expiration
            ttl_expires_at = datetime.now() + timedelta(days=self.default_ttl_days)
            
            # Create full text result
            fulltext_data = {
                'doc_id': doc_id,
                'fulltext_text': text_content,
                'fulltext_storage_uri': source_url,  # Store original URL as storage URI
                'fulltext_fetched_at': datetime.now(),
                'ttl_expires_at': ttl_expires_at,
                'text_length': len(text_content),
                'source_url': source_url,
                'success': True
            }
            
            logger.info(f"Successfully fetched full text for document {doc_id} ({len(text_content)} chars)")
            return fulltext_data
            
        except requests.RequestException as e:
            logger.error(f"Request failed for document {doc_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching full text for document {doc_id}: {e}")
            return None
    
    def _extract_text_from_html(self, html_content: str) -> Optional[str]:
        """
        Extract text content from HTML.
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            Extracted text content or None
        """
        try:
            # Simple text extraction - remove HTML tags and clean up
            # In production, you might want to use BeautifulSoup or similar
            
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', html_content)
            
            # Remove extra whitespace
            text = re.sub(r'\s+', ' ', text)
            
            # Remove common HTML entities
            text = text.replace('&nbsp;', ' ')
            text = text.replace('&amp;', '&')
            text = text.replace('&lt;', '<')
            text = text.replace('&gt;', '>')
            text = text.replace('&quot;', '"')
            
            # Clean up
            text = text.strip()
            
            # Check if we got meaningful content
            if len(text) < 100:  # Too short to be meaningful
                return None
            
            return text
            
        except Exception as e:
            logger.error(f"Error extracting text from HTML: {e}")
            return None
    
    def is_ttl_expired(self, document: Dict[str, Any]) -> bool:
        """
        Check if a document's TTL has expired.
        
        Args:
            document: Document with TTL information
            
        Returns:
            True if TTL has expired
        """
        ttl_expires_at = document.get('ttl_expires_at')
        if not ttl_expires_at:
            return False
        
        if isinstance(ttl_expires_at, str):
            try:
                ttl_expires_at = datetime.fromisoformat(ttl_expires_at)
            except ValueError:
                logger.warning(f"Invalid TTL format for document {document.get('doc_id')}")
                return False
        
        return datetime.now() > ttl_expires_at
    
    def cleanup_expired_fulltext(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Clean up expired full text documents.
        
        Args:
            documents: List of documents to check
            
        Returns:
            List of documents with expired full text cleared
        """
        cleaned_docs = []
        
        for doc in documents:
            if self.is_ttl_expired(doc):
                logger.info(f"Clearing expired full text for document {doc.get('doc_id')}")
                
                # Clear full text fields
                doc['fulltext_text'] = None
                doc['fulltext_storage_uri'] = None
                doc['fulltext_fetched_at'] = None
                doc['ttl_expires_at'] = None
                
                # Update stage back to abstract (stage 1)
                if 'utilities' in doc:
                    for utility in doc['utilities']:
                        if utility.get('stage') == 2:  # Full text stage
                            utility['stage'] = 1  # Back to abstract stage
            
            cleaned_docs.append(doc)
        
        return cleaned_docs
    
    def get_fulltext_stats(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get statistics about full text documents.
        
        Args:
            documents: List of documents to analyze
            
        Returns:
            Dictionary with statistics
        """
        total_docs = len(documents)
        fulltext_docs = sum(1 for doc in documents if doc.get('fulltext_text'))
        expired_docs = sum(1 for doc in documents if self.is_ttl_expired(doc))
        oa_docs = sum(1 for doc in documents if doc.get('is_open_access'))
        
        # Calculate total text size
        total_text_size = sum(
            len(doc.get('fulltext_text', '')) 
            for doc in documents 
            if doc.get('fulltext_text')
        )
        
        return {
            'total_documents': total_docs,
            'fulltext_documents': fulltext_docs,
            'expired_documents': expired_docs,
            'open_access_documents': oa_docs,
            'total_text_size_chars': total_text_size,
            'total_text_size_mb': total_text_size / (1024 * 1024),
            'fulltext_coverage': fulltext_docs / total_docs if total_docs > 0 else 0
        }
