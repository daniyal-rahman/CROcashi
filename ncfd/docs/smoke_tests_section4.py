#!/usr/bin/env python3
"""
Smoke tests for Section 4: Linking Heuristics Implementation

This script tests the core functionality of the linking heuristics system
without requiring a live database or external dependencies.
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Create comprehensive SQLAlchemy mocks
class MockSQLAlchemy:
    """Mock SQLAlchemy module."""
    
    class BigInteger:
        pass
    
    class Integer:
        pass
    
    class String:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    
    class Text:
        pass
    
    class Boolean:
        pass
    
    class DateTime:
        def __init__(self, timezone=None):
            self.timezone = timezone
    
    class Date:
        pass
    
    class Numeric:
        def __init__(self, precision, scale):
            self.precision = precision
            self.scale = scale
    
    class ForeignKey:
        def __init__(self, target, ondelete=None):
            self.target = target
            self.ondelete = ondelete
    
    class Index:
        def __init__(self, name, *columns, **kwargs):
            self.name = name
            self.columns = columns
            self.kwargs = kwargs
    
    class UniqueConstraint:
        def __init__(self, *columns, name=None):
            self.columns = columns
            self.name = name
    
    class CheckConstraint:
        def __init__(self, condition, name=None):
            self.condition = condition
            self.name = name
    
    class PrimaryKeyConstraint:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    
    class func:
        @staticmethod
        def now():
            return "NOW()"
    
    class event:
        @staticmethod
        def listens_for(target, event_name):
            def decorator(func):
                return func
            return decorator
    
    @staticmethod
    def create_engine(*args, **kwargs):
        return Mock()
    
    @staticmethod
    def text(*args, **kwargs):
        return Mock()

class MockSQLAlchemyORM:
    """Mock SQLAlchemy ORM module."""
    
    class DeclarativeBase:
        pass
    
    class Mapped:
        pass
    
    class mapped_column:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    
    class relationship:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    
    class Session:
        pass
    
    @staticmethod
    def sessionmaker(*args, **kwargs):
        return Mock()

class MockPostgreSQL:
    """Mock PostgreSQL dialect module."""
    
    class JSONB:
        pass
    
    class ARRAY:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
    
    class DATERANGE:
        pass
    
    class ENUM:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

# Install mocks
sys.modules['sqlalchemy'] = MockSQLAlchemy()
sys.modules['sqlalchemy.orm'] = MockSQLAlchemyORM()
sys.modules['sqlalchemy.dialects'] = Mock()
sys.modules['sqlalchemy.dialects.postgresql'] = MockPostgreSQL()

# Now import our modules
from ncfd.mapping.linking_heuristics import LinkingHeuristics, LinkPromoter, LinkCandidate
from ncfd.extract.asset_extractor import AssetMatch


class TestLinkCandidate(unittest.TestCase):
    """Test the LinkCandidate dataclass."""
    
    def test_link_candidate_creation(self):
        """Test creating a LinkCandidate with basic fields."""
        candidate = LinkCandidate(
            doc_id=1,
            asset_id=101,
            nct_id="NCT12345678",
            link_type="nct_near_asset",
            confidence=1.00
        )
        
        self.assertEqual(candidate.doc_id, 1)
        self.assertEqual(candidate.asset_id, 101)
        self.assertEqual(candidate.nct_id, "NCT12345678")
        self.assertEqual(candidate.link_type, "nct_near_asset")
        self.assertEqual(candidate.confidence, 1.00)
        self.assertIsInstance(candidate.evidence, dict)
    
    def test_link_candidate_defaults(self):
        """Test LinkCandidate with default values."""
        candidate = LinkCandidate(doc_id=1, asset_id=101)
        
        self.assertIsNone(candidate.nct_id)
        self.assertIsNone(candidate.company_id)
        self.assertEqual(candidate.link_type, "")
        self.assertEqual(candidate.confidence, 0.0)
        self.assertIsInstance(candidate.evidence, dict)


class TestLinkingHeuristics(unittest.TestCase):
    """Test the LinkingHeuristics class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create mock database session
        self.mock_session = Mock()
        self.heuristics = LinkingHeuristics(self.mock_session)
    
    def test_initialization(self):
        """Test LinkingHeuristics initialization."""
        self.assertIsInstance(self.heuristics.phase_keywords, list)
        self.assertIsInstance(self.heuristics.indication_keywords, list)
        self.assertIn('phase i', self.heuristics.phase_keywords)
        self.assertIn('cancer', self.heuristics.indication_keywords)
    
    def test_company_hosted_detection(self):
        """Test company hosting detection logic."""
        # Test company-hosted URL
        company_doc = Mock()
        company_doc.source_url = "https://company.com/press-release"
        self.assertTrue(self.heuristics._is_company_hosted(company_doc))
        
        # Test wire service URL
        wire_doc = Mock()
        wire_doc.source_url = "https://prnewswire.com/releases/company-news"
        self.assertFalse(self.heuristics._is_company_hosted(wire_doc))
        
        # Test None URL
        none_doc = Mock()
        none_doc.source_url = None
        self.assertFalse(self.heuristics._is_company_hosted(none_doc))
    
    def test_combo_wording_detection(self):
        """Test combination therapy wording detection."""
        # Mock document with combo wording
        combo_doc = Mock()
        combo_doc.doc_id = 1
        
        # Mock text pages with combo wording
        mock_page = Mock()
        mock_page.text = "The study evaluated drug A in combination with drug B"
        
        # Mock the query method to return our mock page
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [mock_page]
        self.mock_session.query.return_value = mock_query
        
        self.assertTrue(self.heuristics._detect_combo_wording(combo_doc))
        
        # Mock document without combo wording
        no_combo_doc = Mock()
        no_combo_doc.doc_id = 2
        
        mock_page_no_combo = Mock()
        mock_page_no_combo.text = "The study evaluated drug A alone"
        
        mock_query_no_combo = Mock()
        mock_query_no_combo.filter.return_value.all.return_value = [mock_page_no_combo]
        self.mock_session.query.return_value = mock_query_no_combo
        
        self.assertFalse(self.heuristics._detect_combo_wording(no_combo_doc))
    
    def test_conflict_resolution(self):
        """Test conflict resolution and downgrades."""
        # Mock document without combo wording
        doc = Mock()
        doc.doc_id = 1
        
        # Test without combo wording (should downgrade)
        candidates_no_combo = [
            LinkCandidate(doc_id=1, asset_id=101, confidence=0.90),
            LinkCandidate(doc_id=1, asset_id=102, confidence=0.85)
        ]
        
        with patch.object(self.heuristics, '_detect_combo_wording', return_value=False):
            resolved = self.heuristics._resolve_conflicts(candidates_no_combo, doc)
            
            # Should be downgraded by 0.20
            self.assertAlmostEqual(resolved[0].confidence, 0.70, places=2)
            self.assertAlmostEqual(resolved[1].confidence, 0.65, places=2)
            self.assertEqual(resolved[0].evidence['conflict_resolution'], 'downgraded_multiple_assets')
            self.assertEqual(resolved[1].evidence['conflict_resolution'], 'downgraded_multiple_assets')
        
        # Test with combo wording (no downgrade) - use fresh candidates
        candidates_with_combo = [
            LinkCandidate(doc_id=1, asset_id=101, confidence=0.90),
            LinkCandidate(doc_id=1, asset_id=102, confidence=0.85)
        ]
        
        with patch.object(self.heuristics, '_detect_combo_wording', return_value=True):
            resolved = self.heuristics._resolve_conflicts(candidates_with_combo, doc)
            
            # Should not be downgraded
            self.assertEqual(resolved[0].confidence, 0.90)
            self.assertEqual(resolved[1].confidence, 0.85)
    
    def test_single_candidate_no_conflict(self):
        """Test conflict resolution with single candidate."""
        candidates = [LinkCandidate(doc_id=1, asset_id=101, confidence=0.90)]
        doc = Mock()
        doc.doc_id = 1
        
        resolved = self.heuristics._resolve_conflicts(candidates, doc)
        
        # Should be unchanged
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].confidence, 0.90)


class TestLinkPromoter(unittest.TestCase):
    """Test the LinkPromoter class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_session = Mock()
        self.promoter = LinkPromoter(self.mock_session, confidence_threshold=0.95)
    
    def test_initialization(self):
        """Test LinkPromoter initialization."""
        self.assertEqual(self.promoter.confidence_threshold, 0.95)
        self.assertIs(self.promoter.db_session, self.mock_session)
    
    def test_should_promote_link(self):
        """Test link promotion decision logic."""
        # Test high confidence link
        high_conf_link = Mock()
        high_conf_link.confidence = 0.98
        
        self.assertTrue(self.promoter._should_promote_link(high_conf_link))
        
        # Test low confidence link
        low_conf_link = Mock()
        low_conf_link.confidence = 0.85
        
        self.assertFalse(self.promoter._should_promote_link(low_conf_link))
    
    def test_promote_link(self):
        """Test link promotion process."""
        link = Mock()
        link.doc_id = 1
        link.asset_id = 101
        link.confidence = 0.98
        link.evidence = {}
        
        with patch('ncfd.mapping.linking_heuristics.logger') as mock_logger:
            self.promoter._promote_link(link)
            
            # Check evidence was updated
            self.assertIn('promoted_at', link.evidence)
            self.assertEqual(link.evidence['promoted_at'], 'pending_implementation')
            
            # Check logging
            mock_logger.info.assert_called_once()


class TestAssetMatchIntegration(unittest.TestCase):
    """Test integration with AssetMatch from asset extractor."""
    
    def test_asset_match_creation(self):
        """Test creating AssetMatch objects for heuristics."""
        asset_match = AssetMatch(
            value_text="AB-123",
            value_norm="ab-123",
            alias_type="code",
            page_no=1,
            char_start=100,
            char_end=106,
            detector="regex"
        )
        
        self.assertEqual(asset_match.value_text, "AB-123")
        self.assertEqual(asset_match.value_norm, "ab-123")
        self.assertEqual(asset_match.alias_type, "code")
        self.assertEqual(asset_match.page_no, 1)
        self.assertEqual(asset_match.char_start, 100)
        self.assertEqual(asset_match.char_end, 106)
        self.assertEqual(asset_match.detector, "regex")


def run_smoke_tests():
    """Run all smoke tests and return results."""
    print("🔥 Running Section 4 Linking Heuristics Smoke Tests")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestLinkCandidate))
    suite.addTests(loader.loadTestsFromTestCase(TestLinkingHeuristics))
    suite.addTests(loader.loadTestsFromTestCase(TestLinkPromoter))
    suite.addTests(loader.loadTestsFromTestCase(TestAssetMatchIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("SMOKE TEST RESULTS SUMMARY")
    print("=" * 60)
    
    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED!")
        print(f"   Tests run: {result.testsRun}")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
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
