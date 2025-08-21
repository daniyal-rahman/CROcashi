#!/usr/bin/env python3
"""
Smoke test for Study Card validator
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_validator_import():
    """Test that the validator module can be imported."""
    try:
        from ncfd.extract.validator import (
            validate_card, 
            validate_card_completeness,
            get_coverage_level
        )
        print("✅ Validator module imported successfully")
        return True
    except Exception as e:
        print(f"❌ Validator import failed: {e}")
        return False

def test_schema_loading():
    """Test that the schema can be loaded."""
    try:
        from ncfd.extract.validator import load_schema
        schema = load_schema()
        print(f"✅ Schema loaded successfully")
        print(f"   Title: {schema.get('title', 'N/A')}")
        print(f"   Required fields: {schema.get('required', [])}")
        return True
    except Exception as e:
        print(f"❌ Schema loading failed: {e}")
        return False

def test_coverage_level_detection():
    """Test coverage level detection logic."""
    try:
        from ncfd.extract.validator import get_coverage_level
        
        # Test high coverage card
        high_card = {
            "primary_endpoints": [{"name": "test"}],
            "sample_size": {"total_n": 100},
            "populations": {"analysis_primary_on": "ITT"},
            "results": {"primary": [{"p_value": 0.05}]}
        }
        coverage = get_coverage_level(high_card)
        assert coverage == "high", f"Expected 'high', got '{coverage}'"
        
        # Test medium coverage card
        med_card = {
            "primary_endpoints": [{"name": "test"}],
            "sample_size": {"total_n": 100},
            "populations": {"analysis_primary_on": "ITT"}
            # Missing effect size or p-value
        }
        coverage = get_coverage_level(med_card)
        assert coverage == "med", f"Expected 'med', got '{coverage}'"
        
        # Test low coverage card
        low_card = {
            "primary_endpoints": [{"name": "test"}]
            # Missing most required fields
        }
        coverage = get_coverage_level(low_card)
        assert coverage == "low", f"Expected 'low', got '{coverage}'"
        
        print("✅ Coverage level detection working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Coverage level detection failed: {e}")
        return False

def test_validation_functions():
    """Test that validation functions exist and are callable."""
    try:
        from ncfd.extract.validator import (
            validate_card,
            validate_card_completeness,
            validate_evidence_spans
        )
        
        # Test that functions are callable
        assert callable(validate_card), "validate_card should be callable"
        assert callable(validate_card_completeness), "validate_card_completeness should be callable"
        assert callable(validate_evidence_spans), "validate_evidence_spans should be callable"
        
        print("✅ All validation functions are callable")
        return True
        
    except Exception as e:
        print(f"❌ Validation function test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Study Card Validator")
    print("=" * 40)
    
    tests = [
        test_validator_import,
        test_schema_loading,
        test_coverage_level_detection,
        test_validation_functions
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All validator tests passed!")
        sys.exit(0)
    else:
        print("❌ Some validator tests failed!")
        sys.exit(1)
