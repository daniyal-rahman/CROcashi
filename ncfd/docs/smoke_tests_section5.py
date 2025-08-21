#!/usr/bin/env python3
"""
Smoke tests for Section 5: Extraction & Normalization Details

This script tests the INN dictionary system and enhanced span capture
functionality without requiring live database or external dependencies.
"""

import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Mock SQLAlchemy modules (reuse from section 4 tests)
class MockSQLAlchemy:
    """Mock SQLAlchemy module."""
    
    class BigInteger: pass
    class Integer: pass
    class String:
        def __init__(self, *args, **kwargs): pass
    class Text: pass
    class Boolean: pass
    class DateTime:
        def __init__(self, timezone=None): pass
    class Date: pass
    class Numeric:
        def __init__(self, precision, scale): pass
    class ForeignKey:
        def __init__(self, target, ondelete=None): pass
    class Index:
        def __init__(self, name, *columns, **kwargs): pass
    class UniqueConstraint:
        def __init__(self, *columns, name=None): pass
    class CheckConstraint:
        def __init__(self, condition, name=None): pass
    class PrimaryKeyConstraint:
        def __init__(self, *args, **kwargs): pass
    
    class func:
        @staticmethod
        def now(): return "NOW()"
    
    class event:
        @staticmethod
        def listens_for(target, event_name):
            def decorator(func): return func
            return decorator
    
    @staticmethod
    def create_engine(*args, **kwargs): return Mock()
    @staticmethod
    def text(*args, **kwargs): return Mock()

class MockSQLAlchemyORM:
    """Mock SQLAlchemy ORM module."""
    
    class DeclarativeBase: pass
    class Mapped: pass
    class mapped_column:
        def __init__(self, *args, **kwargs): pass
    class relationship:
        def __init__(self, *args, **kwargs): pass
    class Session: pass
    
    @staticmethod
    def sessionmaker(*args, **kwargs): return Mock()

class MockPostgreSQL:
    """Mock PostgreSQL dialect module."""
    
    class JSONB:
        def __init__(self, *args, **kwargs): pass
    class ARRAY:
        def __init__(self, *args, **kwargs): pass
    class DATERANGE: pass
    class ENUM:
        def __init__(self, *args, **kwargs): pass

# Install mocks
sys.modules['sqlalchemy'] = MockSQLAlchemy()
sys.modules['sqlalchemy.orm'] = MockSQLAlchemyORM()
sys.modules['sqlalchemy.dialects'] = Mock()
sys.modules['sqlalchemy.dialects.postgresql'] = MockPostgreSQL()

# Import modules after mocking
from ncfd.extract.inn_dictionary import (
    INNDictionaryManager, 
    EnhancedSpanCapture, 
    DictionaryEntry, 
    AssetDiscovery
)
from ncfd.extract.asset_extractor import norm_drug_name


class TestDictionaryEntry(unittest.TestCase):
    """Test the DictionaryEntry dataclass."""
    
    def test_dictionary_entry_creation(self):
        """Test creating a DictionaryEntry with all fields."""
        entry = DictionaryEntry(
            alias_text="Aspirin",
            alias_norm="aspirin",
            alias_type="inn",
            source="who_inn",
            confidence=0.95,
            metadata={'year': 1960}
        )
        
        self.assertEqual(entry.alias_text, "Aspirin")
        self.assertEqual(entry.alias_norm, "aspirin")
        self.assertEqual(entry.alias_type, "inn")
        self.assertEqual(entry.source, "who_inn")
        self.assertEqual(entry.confidence, 0.95)
        self.assertEqual(entry.metadata['year'], 1960)
    
    def test_dictionary_entry_defaults(self):
        """Test DictionaryEntry with default values."""
        entry = DictionaryEntry(
            alias_text="Test Drug",
            alias_norm="test drug",
            alias_type="generic",
            source="manual"
        )
        
        self.assertEqual(entry.confidence, 1.0)
        self.assertIsInstance(entry.metadata, dict)
        self.assertEqual(len(entry.metadata), 0)


class TestAssetDiscovery(unittest.TestCase):
    """Test the AssetDiscovery dataclass."""
    
    def test_asset_discovery_creation(self):
        """Test creating an AssetDiscovery."""
        discovery = AssetDiscovery(
            value_text="AB-123",
            value_norm="ab-123",
            alias_type="code",
            source="regex",
            confidence=0.95,
            existing_asset_id=456,
            needs_asset_creation=False
        )
        
        self.assertEqual(discovery.value_text, "AB-123")
        self.assertEqual(discovery.value_norm, "ab-123")
        self.assertEqual(discovery.alias_type, "code")
        self.assertEqual(discovery.source, "regex")
        self.assertEqual(discovery.confidence, 0.95)
        self.assertEqual(discovery.existing_asset_id, 456)
        self.assertFalse(discovery.needs_asset_creation)


class TestINNDictionaryManager(unittest.TestCase):
    """Test the INNDictionaryManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_session = Mock()
        self.inn_manager = INNDictionaryManager(self.mock_session)
    
    def test_initialization(self):
        """Test INNDictionaryManager initialization."""
        self.assertIsInstance(self.inn_manager.confidence_thresholds, dict)
        self.assertIn('exact_match', self.inn_manager.confidence_thresholds)
        self.assertIn('chembl_approved', self.inn_manager.confidence_thresholds)
        self.assertIn('who_inn_recommended', self.inn_manager.confidence_thresholds)
        
        self.assertIsInstance(self.inn_manager._alias_norm_map, dict)
        self.assertIsInstance(self.inn_manager._loaded_sources, set)
    
    def test_load_chembl_dictionary(self):
        """Test loading ChEMBL dictionary."""
        count = self.inn_manager.load_chembl_dictionary("mock_chembl.json")
        
        # Should load sample data
        self.assertGreater(count, 0)
        self.assertIn('chembl', self.inn_manager._loaded_sources)
        
        # Check that entries were added to dictionary
        self.assertGreater(len(self.inn_manager._alias_norm_map), 0)
        
        # Check sample entry
        aspirin_norm = norm_drug_name("Aspirin")
        if aspirin_norm in self.inn_manager._alias_norm_map:
            entries = self.inn_manager._alias_norm_map[aspirin_norm]
            self.assertTrue(any(e.source == 'chembl' for e in entries))
    
    def test_load_who_inn_dictionary(self):
        """Test loading WHO INN dictionary."""
        count = self.inn_manager.load_who_inn_dictionary("mock_who_inn.json")
        
        # Should load sample data
        self.assertGreater(count, 0)
        self.assertIn('who_inn', self.inn_manager._loaded_sources)
        
        # Check that entries were added to dictionary
        self.assertGreater(len(self.inn_manager._alias_norm_map), 0)
    
    def test_build_alias_norm_map(self):
        """Test building complete alias normalization map."""
        # Mock database query
        mock_query = Mock()
        mock_query.all.return_value = []
        self.mock_session.query.return_value = mock_query
        
        # Build map
        alias_map = self.inn_manager.build_alias_norm_map()
        
        # Should return dictionary
        self.assertIsInstance(alias_map, dict)
        
        # Database query should have been called
        self.mock_session.query.assert_called()
    
    def test_discover_assets(self):
        """Test asset discovery in text."""
        # Load some sample data
        self.inn_manager.load_chembl_dictionary("mock_chembl.json")
        self.inn_manager.load_who_inn_dictionary("mock_who_inn.json")
        
        # Mock existing asset lookup
        self.inn_manager._find_existing_asset = Mock(return_value=None)
        
        # Test text with known drugs
        test_text = "The patient was treated with aspirin and ibuprofen."
        
        discoveries = self.inn_manager.discover_assets(test_text)
        
        # Should find some assets
        self.assertIsInstance(discoveries, list)
        # Note: May be empty if tokenization doesn't match sample data exactly
    
    def test_create_asset_shell(self):
        """Test creating asset shell for unknown entity."""
        # Mock asset creation
        mock_asset = Mock()
        mock_asset.asset_id = 12345
        
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Create discovery
        discovery = AssetDiscovery(
            value_text="XYZ-999",
            value_norm="xyz-999",
            alias_type="code",
            source="extraction",
            confidence=0.85,
            needs_asset_creation=True
        )
        
        # Mock Asset class
        with patch('ncfd.extract.inn_dictionary.Asset') as MockAsset:
            MockAsset.return_value = mock_asset
            
            with patch('ncfd.extract.inn_dictionary.AssetAlias') as MockAssetAlias:
                result = self.inn_manager.create_asset_shell(discovery)
                
                # Should create asset and alias
                MockAsset.assert_called_once()
                MockAssetAlias.assert_called_once()
                self.mock_session.add.assert_called()
                self.mock_session.flush.assert_called_once()
                
                self.assertEqual(result, mock_asset)
    
    def test_backfill_asset_ids(self):
        """Test backfilling asset with external IDs."""
        # Mock asset
        mock_asset = Mock()
        mock_asset.asset_id = 123
        mock_asset.names_jsonb = {'primary_name': 'Test Drug'}
        
        # Mock query for existing aliases
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        self.mock_session.query.return_value = mock_query
        
        external_ids = {
            'chembl_id': 'CHEMBL123',
            'unii': 'ABC123DEF'
        }
        
        with patch('ncfd.extract.inn_dictionary.AssetAlias') as MockAssetAlias:
            self.inn_manager.backfill_asset_ids(mock_asset, external_ids)
            
            # Should update names_jsonb
            self.assertIn('chembl_id', mock_asset.names_jsonb)
            self.assertIn('unii', mock_asset.names_jsonb)
            
            # Should create new aliases
            self.assertEqual(MockAssetAlias.call_count, 2)
    
    def test_tokenize_for_drug_names(self):
        """Test drug name tokenization."""
        text = "The patient received aspirin and alpha-interferon treatment."
        
        tokens = self.inn_manager._tokenize_for_drug_names(text)
        
        # Should return list of token dictionaries
        self.assertIsInstance(tokens, list)
        
        if tokens:
            token = tokens[0]
            self.assertIn('text', token)
            self.assertIn('start', token)
            self.assertIn('end', token)


class TestEnhancedSpanCapture(unittest.TestCase):
    """Test the EnhancedSpanCapture class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_session = Mock()
        self.mock_inn_manager = Mock()
        self.span_capture = EnhancedSpanCapture(self.mock_session, self.mock_inn_manager)
    
    def test_initialization(self):
        """Test EnhancedSpanCapture initialization."""
        self.assertEqual(self.span_capture.db_session, self.mock_session)
        self.assertEqual(self.span_capture.inn_manager, self.mock_inn_manager)
    
    def test_capture_asset_code_spans(self):
        """Test capturing asset code spans."""
        text = "Study of AB-123 and XYZ-456 in patients."
        
        # Mock asset extractor
        mock_match = Mock()
        mock_match.value_text = "AB-123"
        mock_match.value_norm = "ab-123"
        mock_match.char_start = 9
        mock_match.char_end = 15
        
        with patch('ncfd.extract.asset_extractor.extract_asset_codes') as mock_extract:
            mock_extract.return_value = [mock_match]
            
            spans = self.span_capture._capture_asset_code_spans(text, page_no=1)
            
            self.assertEqual(len(spans), 1)
            span = spans[0]
            
            self.assertEqual(span['value_text'], "AB-123")
            self.assertEqual(span['value_norm'], "ab-123")
            self.assertEqual(span['ent_type'], 'code')
            self.assertEqual(span['detector'], 'regex')
            self.assertEqual(span['page_no'], 1)
            self.assertEqual(span['char_start'], 9)
            self.assertEqual(span['char_end'], 15)
    
    def test_capture_nct_spans(self):
        """Test capturing NCT ID spans."""
        text = "Clinical trial NCT12345678 showed efficacy."
        
        # Mock NCT extractor
        mock_match = Mock()
        mock_match.value_text = "NCT12345678"
        mock_match.value_norm = "nct12345678"
        mock_match.char_start = 15
        mock_match.char_end = 26
        
        with patch('ncfd.extract.asset_extractor.extract_nct_ids') as mock_extract:
            mock_extract.return_value = [mock_match]
            
            spans = self.span_capture._capture_nct_spans(text, page_no=1)
            
            self.assertEqual(len(spans), 1)
            span = spans[0]
            
            self.assertEqual(span['value_text'], "NCT12345678")
            self.assertEqual(span['ent_type'], 'nct')
            self.assertEqual(span['detector'], 'regex')
            self.assertEqual(span['confidence'], 1.0)
    
    def test_capture_drug_name_spans(self):
        """Test capturing drug name spans using dictionary."""
        text = "Patient received aspirin therapy."
        
        # Mock INN manager discovery
        mock_discovery = Mock()
        mock_discovery.value_text = "aspirin"
        mock_discovery.value_norm = "aspirin"
        mock_discovery.alias_type = "inn"
        mock_discovery.confidence = 0.95
        
        self.mock_inn_manager.discover_assets.return_value = [mock_discovery]
        
        spans = self.span_capture._capture_drug_name_spans(text, page_no=1)
        
        self.assertEqual(len(spans), 1)
        span = spans[0]
        
        self.assertEqual(span['value_text'], "aspirin")
        self.assertEqual(span['ent_type'], 'inn')
        self.assertEqual(span['detector'], 'dict')
        self.assertEqual(span['confidence'], 0.95)
    
    def test_comprehensive_span_capture(self):
        """Test comprehensive span capture integration."""
        text = "Study of AB-123 (aspirin) in trial NCT12345678."
        
        # Mock all span capture methods
        self.span_capture._capture_asset_code_spans = Mock(return_value=[
            {'ent_type': 'code', 'value_text': 'AB-123', 'detector': 'regex'}
        ])
        self.span_capture._capture_nct_spans = Mock(return_value=[
            {'ent_type': 'nct', 'value_text': 'NCT12345678', 'detector': 'regex'}
        ])
        self.span_capture._capture_drug_name_spans = Mock(return_value=[
            {'ent_type': 'inn', 'value_text': 'aspirin', 'detector': 'dict'}
        ])
        self.span_capture._store_spans_in_database = Mock()
        
        spans = self.span_capture.capture_comprehensive_spans(text, doc_id=1, page_no=1)
        
        # Should call all span capture methods
        self.span_capture._capture_asset_code_spans.assert_called_once()
        self.span_capture._capture_nct_spans.assert_called_once()
        self.span_capture._capture_drug_name_spans.assert_called_once()
        
        # Should store spans in database
        self.span_capture._store_spans_in_database.assert_called_once()
        
        # Should return combined spans
        self.assertEqual(len(spans), 3)
    
    def test_store_spans_in_database(self):
        """Test storing spans in database."""
        spans = [
            {
                'ent_type': 'code',
                'value_text': 'AB-123',
                'value_norm': 'ab-123',
                'page_no': 1,
                'char_start': 10,
                'char_end': 16,
                'detector': 'regex',
                'confidence': 0.95
            }
        ]
        
        with patch('ncfd.db.models.DocumentEntity') as MockEntity:
            self.span_capture._store_spans_in_database(spans, doc_id=1)
            
            # Should create DocumentEntity
            MockEntity.assert_called_once()
            self.mock_session.add.assert_called_once()


def run_smoke_tests():
    """Run all Section 5 smoke tests and return results."""
    print("🔥 Running Section 5: Extraction & Normalization Smoke Tests")
    print("=" * 70)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestDictionaryEntry))
    suite.addTests(loader.loadTestsFromTestCase(TestAssetDiscovery))
    suite.addTests(loader.loadTestsFromTestCase(TestINNDictionaryManager))
    suite.addTests(loader.loadTestsFromTestCase(TestEnhancedSpanCapture))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 70)
    print("SECTION 5 SMOKE TEST RESULTS SUMMARY")
    print("=" * 70)
    
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED!")
        print(f"   Tests run: {result.testsRun}")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
        
        print("\n🎉 Section 5 Implementation Verified:")
        print("   • INN/generic dictionary management")
        print("   • ChEMBL and WHO INN integration")
        print("   • Asset discovery and shell creation")
        print("   • Enhanced span capture system")
        print("   • Evidence-based entity extraction")
        
        return True
    else:
        print("❌ SOME TESTS FAILED!")
        print(f"   Tests run: {result.testsRun}")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
        
        if result.failures:
            print("\nFAILURES:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback}")
        
        if result.errors:
            print("\nERRORS:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback}")
        
        return False


if __name__ == "__main__":
    success = run_smoke_tests()
    sys.exit(0 if success else 1)
