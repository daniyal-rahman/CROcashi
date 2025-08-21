"""
Smoke tests for document ingestion module.

These tests verify that the document ingestion functionality works correctly
without requiring a database connection or external web requests.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from ncfd.ingest.document_ingest import DocumentIngester


class TestDocumentIngester:
    """Test document ingestion functionality."""
    
    def test_init(self):
        """Test DocumentIngester initialization."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        assert ingester.db_session == mock_session
        assert ingester.storage_backend is None
        assert ingester.session.headers['User-Agent'] == 'NCFD-Document-Ingester/1.0'
    
    def test_discover_conference_abstracts(self):
        """Test conference abstract source discovery."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        sources = ingester.discover_conference_abstracts()
        
        # Should find sources for all three conferences
        assert len(sources) >= 3
        
        # Check that we have sources for each conference
        publishers = [source['publisher'] for source in sources]
        assert any('AACR' in pub for pub in publishers)
        assert any('ASCO' in pub for pub in publishers)
        assert any('ESMO' in pub for pub in publishers)
        
        # Verify source structure
        for source in sources:
            assert 'url' in source
            assert 'publisher' in source
            assert 'source_type' in source
            assert source['source_type'] == 'Abstract'
    
    def test_get_publisher_from_url(self):
        """Test publisher extraction from URLs."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        # Test AACR URLs
        assert 'AACR' in ingester._get_publisher_from_url('https://aacrjournals.org/cancerres')
        assert 'AACR' in ingester._get_publisher_from_url('https://cancerres.aacrjournals.org')
        
        # Test ASCO URLs
        assert 'ASCO' in ingester._get_publisher_from_url('https://ascopubs.org/journal/jco')
        
        # Test ESMO URLs
        assert 'ESMO' in ingester._get_publisher_from_url('https://www.esmo.org/meetings')
        
        # Test unknown URLs
        assert ingester._get_publisher_from_url('https://unknown.com') == 'Unknown'
    
    def test_is_news_link(self):
        """Test news link detection."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        # Test news-like links
        assert ingester._is_news_link('/news/article-1', 'Latest News')
        assert ingester._is_news_link('/press/release', 'Press Release')
        assert ingester._is_news_link('/media/announcement', 'Company Announcement')
        
        # Test non-news links
        assert not ingester._is_news_link('/about', 'About Us')
        assert not ingester._is_news_link('/contact', 'Contact')
    
    def test_make_absolute_url(self):
        """Test URL conversion to absolute URLs."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        base_url = 'https://example.com/path'
        
        # Test absolute URLs
        assert ingester._make_absolute_url('https://other.com', base_url) == 'https://other.com'
        
        # Test relative URLs
        assert ingester._make_absolute_url('/news', base_url) == 'https://example.com/news'
        assert ingester._make_absolute_url('article', base_url) == 'https://example.com/path/article'
    
    def test_extract_main_content(self):
        """Test main content extraction from HTML."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        # Mock BeautifulSoup object
        mock_soup = Mock()
        
        # Test with article tag
        article_tag = Mock()
        article_tag.get_text.return_value = "Article content here"
        mock_soup.select_one.return_value = article_tag
        
        result = ingester._extract_main_content(mock_soup)
        assert result == article_tag
        
        # Test fallback when no content selectors found
        mock_soup.select_one.return_value = None
        mock_soup.__getitem__ = Mock(return_value=Mock())
        mock_soup.decompose = Mock()
        
        result = ingester._extract_main_content(mock_soup)
        assert result == mock_soup
    
    def test_extract_table_data(self):
        """Test table data extraction."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        # Mock table structure
        mock_table = Mock()
        
        # Mock rows
        mock_row1 = Mock()
        mock_cell1 = Mock()
        mock_cell1.get_text.return_value = "Header 1"
        mock_cell2 = Mock()
        mock_cell2.get_text.return_value = "Header 2"
        mock_row1.find_all.return_value = [mock_cell1, mock_cell2]
        
        mock_row2 = Mock()
        mock_cell3 = Mock()
        mock_cell3.get_text.return_value = "Data 1"
        mock_cell4 = Mock()
        mock_cell4.get_text.return_value = "Data 2"
        mock_row2.find_all.return_value = [mock_cell3, mock_cell4]
        
        mock_table.find_all.return_value = [mock_row1, mock_row2]
        
        result = ingester._extract_table_data(mock_table)
        
        assert result['row_count'] == 2
        assert result['col_count'] == 2
        assert len(result['rows']) == 2
        assert result['rows'][0] == ["Header 1", "Header 2"]
        assert result['rows'][1] == ["Data 1", "Data 2"]
    
    def test_extract_citations(self):
        """Test citation extraction from text."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        test_text = """
        This study references DOI: 10.1000/12345 and PMID: 12345678.
        Another reference: 10.2000/67890
        """
        
        citations = ingester._extract_citations(test_text)
        
        assert 'doi' in citations
        assert 'pmid' in citations
        assert citations['doi'] == '10.1000/12345'  # First DOI found
        assert citations['pmid'] == '12345678'
    
    def test_get_filename_from_url(self):
        """Test filename extraction from URLs."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        # Test with file extension
        assert ingester._get_filename_from_url('https://example.com/document.pdf') == 'document.pdf'
        
        # Test with directory ending
        assert ingester._get_filename_from_url('https://example.com/path/') == 'index.html'
        
        # Test with no path
        assert ingester._get_filename_from_url('https://example.com') == 'index.html'
    
    def test_asset_match_conversion(self):
        """Test AssetMatch conversion methods."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        # Test dict to AssetMatch conversion
        entity_dict = {
            'alias_type': 'code',
            'value_text': 'AB-123',
            'value_norm': 'AB-123',
            'page_no': 1,
            'char_start': 100,
            'char_end': 106,
            'detector': 'regex'
        }
        
        asset_match = ingester._dict_to_asset_match(entity_dict)
        assert asset_match.value_text == 'AB-123'
        assert asset_match.alias_type == 'code'
        assert asset_match.page_no == 1
        
        # Test AssetMatch to dict conversion
        result_dict = ingester._asset_match_to_dict(asset_match)
        assert result_dict['value_text'] == 'AB-123'
        assert result_dict['alias_type'] == 'code'
    
    @patch('ncfd.ingest.document_ingest.extract_all_entities')
    def test_parse_document_html(self, mock_extract_entities):
        """Test HTML document parsing."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        # Mock entity extraction
        mock_extract_entities.return_value = []
        
        # Test HTML parsing
        html_content = b"""
        <html>
            <body>
                <article>
                    <h1>Test Article</h1>
                    <p>This is test content.</p>
                    <table>
                        <tr><td>Header</td></tr>
                        <tr><td>Data</td></tr>
                    </table>
                </article>
            </body>
        </html>
        """
        
        result = ingester.parse_document(html_content, 'text/html', 'https://example.com')
        
        assert 'text_pages' in result
        assert 'tables' in result
        assert 'entities' in result
        assert 'citations' in result
        
        # Should have at least one text page
        assert len(result['text_pages']) > 0
        assert result['text_pages'][0]['page_no'] == 1
    
    def test_parse_document_pdf(self):
        """Test PDF document parsing (minimal implementation)."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        pdf_content = b"%PDF-1.4 fake pdf content"
        
        result = ingester.parse_document(pdf_content, 'application/pdf', 'https://example.com')
        
        assert 'text_pages' in result
        assert len(result['text_pages']) == 1
        assert result['text_pages'][0]['text'] == '[PDF content - parsing not implemented]'
    
    def test_determine_oa_status(self):
        """Test open access status determination."""
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        # Test AACR URLs (should be open)
        assert ingester._determine_oa_status('https://aacrjournals.org', 'text/html', {}) == 'open'
        
        # Test PDF content (should be unknown)
        assert ingester._determine_oa_status('https://example.com', 'application/pdf', {}) == 'unknown'
        
        # Test other URLs (should be unknown)
        assert ingester._determine_oa_status('https://example.com', 'text/html', {}) == 'unknown'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
