#!/usr/bin/env python3
"""
Simple smoke test runner for the NCFD implementation.

This script runs basic tests without requiring pytest or database connections.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_asset_extractor():
    """Test asset extractor functionality."""
    print("Testing asset extractor...")
    
    try:
        from ncfd.extract.asset_extractor import (
            norm_drug_name, extract_asset_codes, extract_nct_ids,
            find_nearby_assets, AssetMatch, get_confidence_for_link_type
        )
        
        # Test drug name normalization
        assert norm_drug_name("α-Tocopherol") == "alpha-tocopherol"
        assert norm_drug_name("β-Carotene") == "beta-carotene"
        assert norm_drug_name("AB-123®") == "ab-123"
        print("  ✅ Drug name normalization: PASSED")
        
        # Test asset code extraction
        test_text = "Our lead compound AB-123 showed promising results with XYZ-456."
        matches = extract_asset_codes(test_text)
        expected_codes = ["AB-123", "XYZ-456"]
        found_codes = [match.value_text for match in matches]
        
        for code in expected_codes:
            assert code in found_codes, f"Expected code {code} not found"
        print("  ✅ Asset code extraction: PASSED")
        
        # Test NCT ID extraction
        test_text = "The trial NCT12345678 enrolled 100 patients."
        matches = extract_nct_ids(test_text)
        assert len(matches) == 1
        assert matches[0].value_norm == "NCT12345678"
        print("  ✅ NCT ID extraction: PASSED")
        
        # Test nearby asset detection
        asset_matches = [
            AssetMatch("AB-123", "AB-123", "code", 1, 100, 106, "regex"),
        ]
        nct_matches = [
            AssetMatch("NCT12345678", "NCT12345678", "nct", 1, 150, 158, "regex"),
        ]
        nearby_pairs = find_nearby_assets(asset_matches, nct_matches)
        assert len(nearby_pairs) == 1
        print("  ✅ Nearby asset detection: PASSED")
        
        # Test confidence scoring
        assert get_confidence_for_link_type('nct_near_asset') == 1.00
        assert get_confidence_for_link_type('code_in_text') == 0.90
        print("  ✅ Confidence scoring: PASSED")
        
        print("  🎉 All asset extractor tests passed!")
        return True
        
    except Exception as e:
        print(f"  ❌ Asset extractor tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_document_ingest():
    """Test document ingestion functionality."""
    print("\nTesting document ingestion...")
    
    try:
        from ncfd.ingest.document_ingest import DocumentIngester
        from unittest.mock import Mock
        
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
        
        print("  🎉 All document ingestion tests passed!")
        return True
        
    except Exception as e:
        print(f"  ❌ Document ingestion tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_models():
    """Test database models."""
    print("\nTesting database models...")
    
    try:
        from ncfd.db.models import (
            Asset, AssetAlias, Document, DocumentTextPage, DocumentTable,
            DocumentLink, DocumentEntity, DocumentCitation, DocumentNote
        )
        
        # Test Asset model
        asset = Asset(
            names_jsonb={"inn": "test_drug"},
            modality="small_molecule",
            target="receptor"
        )
        assert asset.names_jsonb == {"inn": "test_drug"}
        assert asset.modality == "small_molecule"
        print("  ✅ Asset model: PASSED")
        
        # Test AssetAlias model
        alias = AssetAlias(
            asset_id=1,
            alias="AB-123",
            alias_norm="AB-123",
            alias_type="code"
        )
        assert alias.alias == "AB-123"
        assert alias.alias_type == "code"
        print("  ✅ AssetAlias model: PASSED")
        
        # Test Document model
        doc = Document(
            source_type="PR",
            source_url="https://example.com/news",
            storage_uri="file:///tmp/test",
            sha256="a" * 64
        )
        assert doc.source_type == "PR"
        assert doc.sha256 == "a" * 64
        print("  ✅ Document model: PASSED")
        
        # Test other models
        text_page = DocumentTextPage(doc_id=1, page_no=1, char_count=100, text="test")
        table = DocumentTable(doc_id=1, page_no=1, table_idx=0, table_jsonb={})
        link = DocumentLink(doc_id=1, link_type="test", confidence=1.0)
        entity = DocumentEntity(doc_id=1, ent_type="code", value_text="test")
        citation = DocumentCitation(doc_id=1)
        note = DocumentNote(doc_id=1)
        
        print("  ✅ All model instantiation: PASSED")
        
        # Test relationships
        assert hasattr(Asset, 'aliases')
        assert hasattr(Document, 'text_pages')
        assert hasattr(Document, 'links')
        print("  ✅ Model relationships: PASSED")
        
        print("  🎉 All database model tests passed!")
        return True
        
    except Exception as e:
        print(f"  ❌ Database model tests failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all smoke tests."""
    print("NCFD Implementation Smoke Tests")
    print("=" * 40)
    
    results = []
    
    # Run tests
    results.append(test_asset_extractor())
    results.append(test_document_ingest())
    results.append(test_models())
    
    # Summary
    print("\n" + "=" * 40)
    print("TEST SUMMARY")
    print("=" * 40)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"🎉 ALL TESTS PASSED! ({passed}/{total})")
        return 0
    else:
        print(f"❌ SOME TESTS FAILED! ({passed}/{total})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
