#!/usr/bin/env python3
"""
Simple test for document ingestion module only.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_document_ingest():
    """Test document ingestion functionality."""
    print("Testing document ingestion...")
    
    try:
        # Mock SQLAlchemy dependencies
        with patch.dict('sys.modules', {
            'sqlalchemy.orm': Mock(),
            'sqlalchemy': Mock(),
            'ncfd.db.models': Mock(),
            'ncfd.extract.asset_extractor': Mock()
        }):
            from ncfd.ingest.document_ingest import DocumentIngester
            
            # Test initialization
            mock_session = Mock()
            ingester = DocumentIngester(mock_session)
            assert ingester.db_session == mock_session
            assert ingester.session.headers['User-Agent'] == 'NCFD-Document-Ingester/1.0'
            print("  ✅ Initialization: PASSED")
            
            # Test conference source discovery
            sources = ingester.discover_conference_abstracts()
            assert len(sources) >= 3
            publishers = [source['publisher'] for source in sources]
            assert any('AACR' in pub for pub in publishers)
            assert any('ASCO' in pub for pub in publishers)
            assert any('ESMO' in pub for pub in publishers)
            print("  ✅ Conference source discovery: PASSED")
            
            # Test publisher extraction
            assert 'AACR' in ingester._get_publisher_from_url('https://aacrjournals.org')
            assert 'ASCO' in ingester._get_publisher_from_url('https://ascopubs.org')
            assert 'ESMO' in ingester._get_publisher_from_url('https://esmo.org')
            print("  ✅ Publisher extraction: PASSED")
            
            # Test URL utilities
            assert ingester._make_absolute_url('/news', 'https://example.com/path') == 'https://example.com/news'
            assert ingester._is_news_link('/news/article', 'Latest News')
            print("  ✅ URL utilities: PASSED")
            
            # Test filename extraction
            assert ingester._get_filename_from_url('https://example.com/document.pdf') == 'document.pdf'
            assert ingester._get_filename_from_url('https://example.com/path/') == 'index.html'
            print("  ✅ Filename extraction: PASSED")
            
            print("  🎉 All document ingestion tests passed!")
            return True
            
    except Exception as e:
        print(f"  ❌ Document ingestion tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_document_ingest()
    if success:
        print("\n🎉 SUCCESS: Document ingestion is working correctly!")
        sys.exit(0)
    else:
        print("\n❌ FAILURE: Document ingestion has issues!")
        sys.exit(1)
