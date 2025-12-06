#!/usr/bin/env python
"""
Quick verification script to check if tests can be imported and basic structure is correct.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

def verify_imports():
    """Verify all imports work."""
    try:
        from database.config import SessionLocal
        print("✓ database.config imported")
        
        from database.models import (
            Company, Drug, Disease, ClinicalTrial, TrialStatusHistory,
            FDAApplication, FDASubmission, StockPrice, HistoricalCatalyst
        )
        print("✓ database.models imported")
        
        from database.models.relationships import TrialSponsor, TrialDisease
        print("✓ database.models.relationships imported")
        
        from src.backtesting.catalyst_extractor import (
            extract_fda_catalysts,
            extract_trial_catalysts,
            compute_stock_reaction,
            load_catalysts
        )
        print("✓ src.backtesting.catalyst_extractor imported")
        
        import pytest
        print("✓ pytest imported")
        
        return True
    except Exception as e:
        print(f"✗ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_test_file():
    """Verify test file exists and can be parsed."""
    test_file = os.path.join(os.path.dirname(__file__), 'test_catalyst_extractor.py')
    if not os.path.exists(test_file):
        print(f"✗ Test file not found: {test_file}")
        return False
    
    try:
        with open(test_file, 'r') as f:
            content = f.read()
        
        # Check for key test classes
        required_classes = [
            'TestExtractFDACatalysts',
            'TestExtractTrialCatalysts',
            'TestComputeStockReaction',
            'TestLoadCatalysts',
            'TestDataVerification'
        ]
        
        for cls in required_classes:
            if f'class {cls}' in content:
                print(f"✓ Found test class: {cls}")
            else:
                print(f"✗ Missing test class: {cls}")
                return False
        
        return True
    except Exception as e:
        print(f"✗ Error reading test file: {e}")
        return False

if __name__ == "__main__":
    print("Verifying test setup...")
    print("=" * 60)
    
    imports_ok = verify_imports()
    test_file_ok = verify_test_file()
    
    print("=" * 60)
    if imports_ok and test_file_ok:
        print("✓ All verifications passed!")
        print("\nTo run tests, use:")
        print("  pytest tests/backtesting/test_catalyst_extractor.py -v")
        sys.exit(0)
    else:
        print("✗ Some verifications failed")
        sys.exit(1)
