"""
Unit tests for the SEC Filings Client.

Tests all document fetching, parsing, section extraction, and rate limiting capabilities.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json
import hashlib

from src.ncfd.ingest.sec_filings import SecFilingsClient
from src.ncfd.ingest.sec_types import (
    FilingMetadata, DocumentSection, FilingDocument, FilingType
)


class TestSecFilingsClient:
    """Test SEC filings client functionality."""
    
    @pytest.fixture
    def client(self):
        """Create a test client instance."""
        config = {
            'api': {
                'base_url': 'https://www.sec.gov/Archives/edgar/data',
                'timeout': 30,
                'max_retries': 3,
                'retry_delay': 1
            },
            'rate_limiting': {
                'requests_per_second': 2,
                'burst_limit': 10,
                'exponential_backoff': True
            },
            'parsing': {
                'max_document_size_mb': 50,
                'extract_sections': True,
                'section_strategies': ['html_outline', 'regex', 'manual']
            },
            'caching': {
                'enabled': True,
                'ttl_hours': 24
            }
        }
        return SecFilingsClient(config)
    
    def test_client_initialization(self, client):
        """Test client initialization."""
        assert client.base_url == 'https://www.sec.gov/Archives/edgar/data'
        assert client.timeout == 30
        assert client.max_retries == 3
        assert client.retry_delay == 1
        assert client.requests_per_second == 2
        assert client.burst_limit == 10
        assert client.exponential_backoff is True
        assert client.max_document_size_mb == 50
        assert client.extract_sections is True
        assert len(client.section_strategies) == 3
        assert client.caching_enabled is True
        assert client.cache_ttl_hours == 24
    
    @patch('requests.get')
    def test_fetch_filing_metadata(self, mock_get, client):
        """Test fetching filing metadata."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "filings": [
                {
                    "cik": "0001234567",
                    "companyName": "Test Company",
                    "formType": "8-K",
                    "filingDate": "2024-01-15",
                    "accessionNumber": "0001234567-24-000001",
                    "primaryDocument": "test-doc.txt",
                    "description": "Test filing"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Test fetching metadata
        filings = client.fetch_filing_metadata(
            cik="0001234567",
            form_type="8-K",
            start_date="2024-01-01",
            end_date="2024-01-31"
        )
        
        assert len(filings) == 1
        assert filings[0]["cik"] == "0001234567"
        assert filings[0]["formType"] == "8-K"
        assert filings[0]["filingDate"] == "2024-01-15"
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "sec.gov" in call_args[0][0]
    
    @patch('requests.get')
    def test_fetch_filing_document(self, mock_get, client):
        """Test fetching filing document."""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        <DOCUMENT>
        <TYPE>8-K
        <SEQUENCE>1
        <FILENAME>test-doc.txt
        <DESCRIPTION>Test document
        <TEXT>
        <html>
        <body>
        <h1>Item 1.01</h1>
        <p>Test content for Item 1.01</p>
        <h1>Item 8.01</h1>
        <p>Test content for Item 8.01</p>
        </body>
        </html>
        </TEXT>
        </DOCUMENT>
        """
        mock_get.return_value = mock_response
        
        # Test fetching document
        document = client.fetch_filing_document(
            cik="0001234567",
            accession_number="0001234567-24-000001",
            document_path="test-doc.txt"
        )
        
        assert document is not None
        assert document.cik == "0001234567"
        assert document.accession_number == "0001234567-24-000001"
        assert document.document_path == "test-doc.txt"
        assert document.content is not None
        assert "Item 1.01" in document.content
        assert "Item 8.01" in document.content
        
        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "test-doc.txt" in call_args[0][0]
    
    @patch('requests.get')
    def test_fetch_filing_document_not_found(self, mock_get, client):
        """Test fetching filing document when not found."""
        # Mock API response for not found
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        # Test fetching non-existent document
        document = client.fetch_filing_document(
            cik="0001234567",
            accession_number="0001234567-24-000001",
            document_path="non-existent.txt"
        )
        
        assert document is None
    
    @patch('requests.get')
    def test_fetch_filing_document_api_error(self, mock_get, client):
        """Test handling API errors when fetching document."""
        # Mock API response for error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response
        
        # Test error handling
        with pytest.raises(Exception, match="Failed to fetch document"):
            client.fetch_filing_document(
                cik="0001234567",
                accession_number="0001234567-24-000001",
                document_path="test-doc.txt"
            )
    
    def test_extract_sections_html_outline(self, client):
        """Test section extraction using HTML outline strategy."""
        # Sample HTML content
        html_content = """
        <html>
        <body>
        <h1>Item 1.01</h1>
        <p>Content for Item 1.01</p>
        <h2>Subsection 1.01.1</h2>
        <p>Subsection content</p>
        <h1>Item 8.01</h1>
        <p>Content for Item 8.01</p>
        <h1>Item 9.01</h1>
        <p>Content for Item 9.01</p>
        </body>
        </html>
        """
        
        # Extract sections using HTML outline strategy
        sections = client._extract_sections_html_outline(html_content)
        
        assert len(sections) == 3
        assert sections[0].section_name == "Item 1.01"
        assert "Content for Item 1.01" in sections[0].content
        assert sections[1].section_name == "Item 8.01"
        assert "Content for Item 8.01" in sections[0].content
        assert sections[2].section_name == "Item 9.01"
        assert "Content for Item 9.01" in sections[0].content
    
    def test_extract_sections_regex(self, client):
        """Test section extraction using regex strategy."""
        # Sample text content
        text_content = """
        Item 1.01 Entry into a Material Definitive Agreement
        
        Test content for Item 1.01
        
        Item 8.01 Other Events
        
        Test content for Item 8.01
        
        Item 9.01 Financial Statements and Exhibits
        
        Test content for Item 9.01
        """
        
        # Extract sections using regex strategy
        sections = client._extract_sections_regex(text_content)
        
        assert len(sections) == 3
        assert sections[0].section_name == "Item 1.01"
        assert "Entry into a Material Definitive Agreement" in sections[0].content
        assert sections[1].section_name == "Item 8.01"
        assert "Other Events" in sections[1].content
        assert sections[2].section_name == "Item 9.01"
        assert "Financial Statements and Exhibits" in sections[2].content
    
    def test_extract_sections_manual(self, client):
        """Test section extraction using manual delimiters."""
        # Sample text content with manual delimiters
        text_content = """
        =ITEM 1.01=
        Entry into a Material Definitive Agreement
        
        Test content for Item 1.01
        
        =ITEM 8.01=
        Other Events
        
        Test content for Item 8.01
        
        =ITEM 9.01=
        Financial Statements and Exhibits
        
        Test content for Item 9.01
        """
        
        # Extract sections using manual strategy
        sections = client._extract_sections_manual(text_content)
        
        assert len(sections) == 3
        assert sections[0].section_name == "Item 1.01"
        assert "Entry into a Material Definitive Agreement" in sections[0].content
        assert sections[1].section_name == "Item 8.01"
        assert "Other Events" in sections[1].content
        assert sections[2].section_name == "Item 9.01"
        assert "Financial Statements and Exhibits" in sections[2].content
    
    def test_extract_sections_fallback(self, client):
        """Test section extraction with fallback strategies."""
        # Sample content that might not work well with HTML outline
        content = """
        Item 1.01 Entry into a Material Definitive Agreement
        
        Test content for Item 1.01
        
        Item 8.01 Other Events
        
        Test content for Item 8.01
        """
        
        # Extract sections with fallback
        sections = client.extract_sections(content)
        
        assert len(sections) >= 2
        assert any(s.section_name == "Item 1.01" for s in sections)
        assert any(s.section_name == "Item 8.01" for s in sections)
    
    def test_parse_filing_content(self, client):
        """Test parsing filing content."""
        # Sample filing content
        filing_content = """
        <DOCUMENT>
        <TYPE>8-K
        <SEQUENCE>1
        <FILENAME>test-doc.txt
        <DESCRIPTION>Test document
        <TEXT>
        <html>
        <body>
        <h1>Item 1.01</h1>
        <p>Test content for Item 1.01</p>
        <h1>Item 8.01</h1>
        <p>Test content for Item 8.01</p>
        </body>
        </html>
        </TEXT>
        </DOCUMENT>
        """
        
        # Parse filing content
        parsed_content = client._parse_filing_content(filing_content)
        
        assert parsed_content is not None
        assert "Item 1.01" in parsed_content
        assert "Item 8.01" in parsed_content
        assert "<html>" in parsed_content
        assert "<body>" in parsed_content
    
    def test_parse_filing_content_invalid(self, client):
        """Test parsing invalid filing content."""
        # Invalid content
        invalid_content = "Invalid content without proper structure"
        
        # Parse filing content
        parsed_content = client._parse_filing_content(invalid_content)
        
        # Should return the original content or handle gracefully
        assert parsed_content is not None
    
    def test_calculate_content_hash(self, client):
        """Test content hash calculation."""
        # Sample content
        content = "Test content for hashing"
        
        # Calculate hash
        content_hash = client._calculate_content_hash(content)
        
        # Verify hash format
        assert len(content_hash) == 64  # SHA-256 hex length
        assert content_hash == hashlib.sha256(content.encode()).hexdigest()
    
    def test_is_content_changed(self, client):
        """Test content change detection."""
        # Original content
        original_content = "Original content"
        original_hash = client._calculate_content_hash(original_content)
        
        # Same content
        same_content = "Original content"
        same_hash = client._calculate_content_hash(same_content)
        
        # Different content
        different_content = "Different content"
        different_hash = client._calculate_content_hash(different_content)
        
        # Test change detection
        assert not client._is_content_changed(original_hash, same_hash)
        assert client._is_content_changed(original_hash, different_hash)
    
    def test_rate_limiting(self, client):
        """Test rate limiting functionality."""
        # Test that rate limiting is properly configured
        assert client.requests_per_second == 2
        assert client.burst_limit == 10
        assert client.exponential_backoff is True
        
        # Test rate limiting delay calculation
        delay = client._calculate_rate_limit_delay()
        assert delay >= 0.5  # Should be at least 0.5 seconds for 2 req/s
    
    def test_exponential_backoff(self, client):
        """Test exponential backoff functionality."""
        # Test backoff calculation
        backoff_1 = client._calculate_backoff_delay(1)
        backoff_2 = client._calculate_backoff_delay(2)
        backoff_3 = client._calculate_backoff_delay(3)
        
        # Each retry should have longer delay
        assert backoff_2 > backoff_1
        assert backoff_3 > backoff_2
        
        # Should not exceed max delay
        max_backoff = client.retry_delay * (2 ** (client.max_retries - 1))
        assert backoff_3 <= max_backoff
    
    def test_caching(self, client):
        """Test caching functionality."""
        # Test cache key generation
        cache_key = client._generate_cache_key(
            cik="0001234567",
            accession_number="0001234567-24-000001",
            document_path="test-doc.txt"
        )
        
        assert cache_key is not None
        assert "0001234567" in cache_key
        assert "0001234567-24-000001" in cache_key
        assert "test-doc.txt" in cache_key
    
    def test_validate_cik(self, client):
        """Test CIK validation."""
        # Test valid CIK
        assert client._validate_cik("0001234567") is True
        assert client._validate_cik("1234567") is True  # Should pad with zeros
        
        # Test invalid CIK
        assert client._validate_cik("123") is False  # Too short
        assert client._validate_cik("12345678901") is False  # Too long
        assert client._validate_cik("abc1234567") is False  # Contains letters
    
    def test_validate_accession_number(self, client):
        """Test accession number validation."""
        # Test valid accession number
        assert client._validate_accession_number("0001234567-24-000001") is True
        
        # Test invalid accession number
        assert client._validate_accession_number("1234567-24-000001") is False  # Missing leading zeros
        assert client._validate_accession_number("0001234567-24-00001") is False  # Wrong format
        assert client._validate_accession_number("0001234567-24-000001-extra") is False  # Extra content
    
    def test_build_document_url(self, client):
        """Test document URL building."""
        # Test URL building
        url = client._build_document_url(
            cik="0001234567",
            accession_number="0001234567-24-000001",
            document_path="test-doc.txt"
        )
        
        assert "sec.gov" in url
        assert "0001234567" in url
        assert "0001234567-24-000001" in url
        assert "test-doc.txt" in url
    
    def test_error_handling(self, client):
        """Test error handling functionality."""
        # Test handling of invalid CIK
        with pytest.raises(ValueError, match="Invalid CIK format"):
            client.fetch_filing_document(
                cik="INVALID_CIK",
                accession_number="0001234567-24-000001",
                document_path="test-doc.txt"
            )
        
        # Test handling of invalid accession number
        with pytest.raises(ValueError, match="Invalid accession number format"):
            client.fetch_filing_document(
                cik="0001234567",
                accession_number="INVALID_ACCESSION",
                document_path="test-doc.txt"
            )
        
        # Test handling of empty document path
        with pytest.raises(ValueError, match="Document path cannot be empty"):
            client.fetch_filing_document(
                cik="0001234567",
                accession_number="0001234567-24-000001",
                document_path=""
            )
    
    def test_document_size_validation(self, client):
        """Test document size validation."""
        # Test small document
        small_content = "Small content"
        assert client._validate_document_size(small_content) is True
        
        # Test large document (mock)
        large_content = "x" * (client.max_document_size_mb * 1024 * 1024 + 1)
        assert client._validate_document_size(large_content) is False
    
    def test_section_validation(self, client):
        """Test section validation."""
        # Test valid section
        valid_section = DocumentSection(
            section_name="Item 1.01",
            content="Test content",
            start_position=0,
            end_position=100,
            confidence=0.9
        )
        assert client._validate_section(valid_section) is True
        
        # Test invalid section (empty content)
        invalid_section = DocumentSection(
            section_name="Item 1.01",
            content="",
            start_position=0,
            end_position=0,
            confidence=0.9
        )
        assert client._validate_section(invalid_section) is False


class TestSecFilingsClientIntegration:
    """Integration tests for the SEC filings client."""
    
    @pytest.fixture
    def client(self):
        """Create a test client instance."""
        config = {
            'api': {
                'base_url': 'https://www.sec.gov/Archives/edgar/data',
                'timeout': 30,
                'max_retries': 3,
                'retry_delay': 1
            },
            'rate_limiting': {
                'requests_per_second': 2,
                'burst_limit': 10,
                'exponential_backoff': True
            },
            'parsing': {
                'max_document_size_mb': 50,
                'extract_sections': True,
                'section_strategies': ['html_outline', 'regex', 'manual']
            },
            'caching': {
                'enabled': True,
                'ttl_hours': 24
            }
        }
        return SecFilingsClient(config)
    
    @patch('requests.get')
    def test_end_to_end_filing_workflow(self, mock_get, client):
        """Test complete end-to-end filing workflow."""
        # Mock API response for metadata
        metadata_response = Mock()
        metadata_response.status_code = 200
        metadata_response.json.return_value = {
            "filings": [
                {
                    "cik": "0001234567",
                    "companyName": "Test Company",
                    "formType": "8-K",
                    "filingDate": "2024-01-15",
                    "accessionNumber": "0001234567-24-000001",
                    "primaryDocument": "test-doc.txt",
                    "description": "Test filing"
                }
            ]
        }
        
        # Mock API response for document
        document_response = Mock()
        document_response.status_code = 200
        document_response.text = """
        <DOCUMENT>
        <TYPE>8-K
        <SEQUENCE>1
        <FILENAME>test-doc.txt
        <DESCRIPTION>Test document
        <TEXT>
        <html>
        <body>
        <h1>Item 1.01</h1>
        <p>Entry into a Material Definitive Agreement</p>
        <p>Test content for Item 1.01</p>
        <h1>Item 8.01</h1>
        <p>Other Events</p>
        <p>Test content for Item 8.01</p>
        </body>
        </html>
        </TEXT>
        </DOCUMENT>
        """
        
        # Configure mock to return different responses
        mock_get.side_effect = [metadata_response, document_response]
        
        # Fetch metadata
        filings = client.fetch_filing_metadata(
            cik="0001234567",
            form_type="8-K",
            start_date="2024-01-01",
            end_date="2024-01-31"
        )
        
        assert len(filings) == 1
        filing = filings[0]
        
        # Fetch document for the first filing
        document = client.fetch_filing_document(
            cik=filing["cik"],
            accession_number=filing["accessionNumber"],
            document_path=filing["primaryDocument"]
        )
        
        assert document is not None
        assert document.cik == filing["cik"]
        assert document.accession_number == filing["accessionNumber"]
        
        # Extract sections
        sections = client.extract_sections(document.content)
        
        assert len(sections) >= 2
        assert any(s.section_name == "Item 1.01" for s in sections)
        assert any(s.section_name == "Item 8.01" for s in sections)
        
        # Verify API calls
        assert mock_get.call_count == 2
    
    def test_section_extraction_strategies(self, client):
        """Test different section extraction strategies."""
        # Test HTML content
        html_content = """
        <html>
        <body>
        <h1>Item 1.01</h1>
        <p>Test content for Item 1.01</p>
        <h1>Item 8.01</h1>
        <p>Test content for Item 8.01</p>
        </body>
        </html>
        """
        
        html_sections = client._extract_sections_html_outline(html_content)
        assert len(html_sections) == 2
        
        # Test text content with regex patterns
        text_content = """
        Item 1.01 Entry into a Material Definitive Agreement
        
        Test content for Item 1.01
        
        Item 8.01 Other Events
        
        Test content for Item 8.01
        """
        
        regex_sections = client._extract_sections_regex(text_content)
        assert len(regex_sections) == 2
        
        # Test manual delimiters
        manual_content = """
        =ITEM 1.01=
        Test content for Item 1.01
        
        =ITEM 8.01=
        Test content for Item 8.01
        """
        
        manual_sections = client._extract_sections_manual(manual_content)
        assert len(manual_sections) == 2
    
    def test_content_change_detection_workflow(self, client):
        """Test complete content change detection workflow."""
        # Original content
        original_content = "Original filing content"
        original_hash = client._calculate_content_hash(original_content)
        
        # Same content (no changes)
        same_content = "Original filing content"
        same_hash = client._calculate_content_hash(same_content)
        
        # Different content (changes)
        different_content = "Updated filing content with changes"
        different_hash = client._calculate_content_hash(different_content)
        
        # Test change detection
        assert not client._is_content_changed(original_hash, same_hash)
        assert client._is_content_changed(original_hash, different_hash)
        
        # Test with filing document objects
        original_doc = FilingDocument(
            cik="0001234567",
            accession_number="0001234567-24-000001",
            document_path="test-doc.txt",
            content=original_content,
            content_hash=original_hash,
            fetched_at=datetime.utcnow()
        )
        
        updated_doc = FilingDocument(
            cik="0001234567",
            accession_number="0001234567-24-000001",
            document_path="test-doc.txt",
            content=different_content,
            content_hash=different_hash,
            fetched_at=datetime.utcnow()
        )
        
        # Check if documents are different
        assert original_doc.content_hash != updated_doc.content_hash
        assert client._is_content_changed(original_doc.content_hash, updated_doc.content_hash)


if __name__ == "__main__":
    pytest.main([__file__])
