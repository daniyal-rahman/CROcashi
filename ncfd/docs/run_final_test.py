#!/usr/bin/env python3
"""
Final comprehensive test for the NCFD implementation.

This script tests the core functionality that doesn't require database connections.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_core_functionality():
    """Test core functionality without database dependencies."""
    print("NCFD Implementation - Core Functionality Test")
    print("=" * 50)
    
    results = []
    
    # Test 1: Asset Extractor
    print("\n1. Testing Asset Extractor...")
    try:
        from ncfd.extract.asset_extractor import (
            norm_drug_name, extract_asset_codes, extract_nct_ids,
            find_nearby_assets, AssetMatch, get_confidence_for_link_type
        )
        
        # Test normalization
        assert norm_drug_name("α-Tocopherol") == "alpha-tocopherol"
        assert norm_drug_name("β-Carotene") == "beta-carotene"
        assert norm_drug_name("AB-123®") == "ab-123"
        
        # Test asset code extraction
        test_text = "Our lead compound AB-123 showed promising results with XYZ-456."
        matches = extract_asset_codes(test_text)
        expected_codes = ["AB-123", "XYZ-456"]
        found_codes = [match.value_text for match in matches]
        for code in expected_codes:
            assert code in found_codes
        
        # Test NCT extraction
        test_text = "The trial NCT12345678 enrolled 100 patients."
        matches = extract_nct_ids(test_text)
        assert len(matches) == 1
        assert matches[0].value_norm == "NCT12345678"
        
        # Test nearby detection
        asset_matches = [AssetMatch("AB-123", "AB-123", "code", 1, 100, 106, "regex")]
        nct_matches = [AssetMatch("NCT12345678", "NCT12345678", "nct", 1, 150, 158, "regex")]
        nearby_pairs = find_nearby_assets(asset_matches, nct_matches)
        assert len(nearby_pairs) == 1
        
        # Test confidence scoring
        assert get_confidence_for_link_type('nct_near_asset') == 1.00
        assert get_confidence_for_link_type('code_in_text') == 0.90
        
        print("   ✅ Asset Extractor: PASSED")
        results.append(True)
        
    except Exception as e:
        print(f"   ❌ Asset Extractor: FAILED - {e}")
        results.append(False)
    
    # Test 2: Document Ingestion (Core Logic)
    print("\n2. Testing Document Ingestion Core Logic...")
    try:
        from ncfd.ingest.document_ingest import DocumentIngester
        from unittest.mock import Mock
        
        # Test with mocked session
        mock_session = Mock()
        ingester = DocumentIngester(mock_session)
        
        # Test conference discovery
        sources = ingester.discover_conference_abstracts()
        assert len(sources) >= 3
        
        # Test publisher extraction
        assert 'AACR' in ingester._get_publisher_from_url('https://aacrjournals.org')
        assert 'ASCO' in ingester._get_publisher_from_url('https://ascopubs.org')
        assert 'ESMO' in ingester._get_publisher_from_url('https://esmo.org')
        
        # Test URL utilities
        assert ingester._make_absolute_url('/news', 'https://example.com/path') == 'https://example.com/news'
        assert ingester._is_news_link('/news/article', 'Latest News')
        
        print("   ✅ Document Ingestion Core: PASSED")
        results.append(True)
        
    except Exception as e:
        print(f"   ❌ Document Ingestion Core: FAILED - {e}")
        results.append(False)
    
    # Test 3: File Structure and Imports
    print("\n3. Testing File Structure and Imports...")
    try:
        # Check that all required files exist
        required_files = [
            "src/ncfd/extract/asset_extractor.py",
            "src/ncfd/ingest/document_ingest.py",
            "src/ncfd/db/models.py",
            "alembic/versions/20250121_create_document_staging_and_assets.py"
        ]
        
        for file_path in required_files:
            assert Path(file_path).exists(), f"Missing file: {file_path}"
        
        print("   ✅ File Structure: PASSED")
        results.append(True)
        
    except Exception as e:
        print(f"   ❌ File Structure: FAILED - {e}")
        results.append(False)
    
    # Test 4: Alembic Migration
    print("\n4. Testing Alembic Migration...")
    try:
        migration_file = Path("alembic/versions/20250121_create_document_staging_and_assets.py")
        assert migration_file.exists()
        
        # Check migration content
        content = migration_file.read_text()
        assert "documents" in content
        assert "assets" in content
        assert "asset_aliases" in content
        assert "document_links" in content
        assert "upgrade()" in content
        assert "downgrade()" in content
        
        print("   ✅ Alembic Migration: PASSED")
        results.append(True)
        
    except Exception as e:
        print(f"   ❌ Alembic Migration: FAILED - {e}")
        results.append(False)
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Tests Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 ALL CORE TESTS PASSED!")
        print("\nThe NCFD implementation is working correctly:")
        print("✅ Asset extraction and normalization")
        print("✅ Document ingestion logic")
        print("✅ File structure and organization")
        print("✅ Database migration setup")
        print("\nNext steps:")
        print("1. Install SQLAlchemy and other dependencies")
        print("2. Run the Alembic migration")
        print("3. Test with actual database connection")
        return 0
    else:
        print("❌ SOME TESTS FAILED!")
        print(f"Failed tests: {total - passed}")
        return 1


if __name__ == "__main__":
    sys.exit(test_core_functionality())
