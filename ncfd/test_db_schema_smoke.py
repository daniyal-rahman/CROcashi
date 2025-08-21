#!/usr/bin/env python3
"""
Smoke test for database schema changes
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_study_model_import():
    """Test that the Study model can be imported."""
    try:
        from ncfd.db.models import Study
        print("✅ Study model imported successfully")
        return True
    except Exception as e:
        print(f"❌ Study model import failed: {e}")
        return False

def test_study_model_structure():
    """Test that the Study model has the expected structure."""
    try:
        from ncfd.db.models import Study
        
        # Check required fields
        required_fields = ['study_id', 'trial_id', 'doc_type', 'year', 'extracted_jsonb', 'coverage_level']
        for field in required_fields:
            assert hasattr(Study, field), f"Study model missing field: {field}"
        
        print("✅ Study model has expected structure")
        return True
        
    except Exception as e:
        print(f"❌ Study model structure test failed: {e}")
        return False

def test_document_link_relationship():
    """Test that DocumentLink has the study relationship."""
    try:
        from ncfd.db.models import DocumentLink
        
        # Check that study_id field exists
        assert hasattr(DocumentLink, 'study_id'), "DocumentLink missing study_id field"
        
        print("✅ DocumentLink has study relationship")
        return True
        
    except Exception as e:
        print(f"❌ DocumentLink relationship test failed: {e}")
        return False

def test_trial_relationship():
    """Test that Study has the trial relationship."""
    try:
        from ncfd.db.models import Study
        
        # Check that trial relationship exists
        assert hasattr(Study, 'trial'), "Study missing trial relationship"
        
        print("✅ Study has trial relationship")
        return True
        
    except Exception as e:
        print(f"❌ Trial relationship test failed: {e}")
        return False

def test_table_args():
    """Test that Study model has proper table configuration."""
    try:
        from ncfd.db.models import Study
        
        # Check that __table_args__ exists
        assert hasattr(Study, '__table_args__'), "Study missing __table_args__"
        
        # Check that indexes are defined
        table_args = Study.__table_args__
        assert len(table_args) > 0, "Study __table_args__ should contain indexes"
        
        print("✅ Study model has proper table configuration")
        return True
        
    except Exception as e:
        print(f"❌ Table args test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Database Schema Changes")
    print("=" * 40)
    
    tests = [
        test_study_model_import,
        test_study_model_structure,
        test_document_link_relationship,
        test_trial_relationship,
        test_table_args
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All database schema tests passed!")
        sys.exit(0)
    else:
        print("❌ Some database schema tests failed!")
        sys.exit(1)
