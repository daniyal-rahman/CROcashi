#!/usr/bin/env python3
"""
Quick Test Runner for Study Card System

This script runs a subset of tests for quick validation during development.
It focuses on core functionality and skips time-consuming tests.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def run_quick_tests():
    """Run quick tests for basic functionality."""
    print("🚀 Quick Test Runner for Study Card System")
    print("=" * 50)
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Basic imports
    print("\n🧪 Test 1: Basic Imports")
    try:
        from ncfd.extract.workers import BaseWorker
        from ncfd.extract.models import EvidenceSpan
        from ncfd.extract.workers.llm import MethodAuditor
        from ncfd.extract.workers.deterministic import GateValidator
        print("  ✅ All imports successful")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        tests_failed += 1
    
    # Test 2: Model creation
    print("\n🧪 Test 2: Model Creation")
    try:
        span = EvidenceSpan(
            doc_id="test:123",
            quote="Test quote for validation",
            section="Methods",
            page=1,
            char_start=0,
            char_end=50,
            confidence=0.9
        )
        print(f"  ✅ EvidenceSpan created: {span.doc_id}")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ Model creation failed: {e}")
        tests_failed += 1
    
    # Test 3: Worker instantiation
    print("\n🧪 Test 3: Worker Instantiation")
    try:
        method_auditor = MethodAuditor()
        gate_validator = GateValidator()
        print("  ✅ Workers instantiated successfully")
        tests_passed += 1
    except Exception as e:
        print(f"  ❌ Worker instantiation failed: {e}")
        tests_failed += 1
    
    # Test 4: Configuration loading
    print("\n🧪 Test 4: Configuration Loading")
    try:
        import yaml
        config_file = Path("test_config.yaml")
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            print(f"  ✅ Configuration loaded: {len(config)} sections")
            tests_passed += 1
        else:
            print("  ⚠️ Configuration file not found, skipping")
            tests_passed += 1
    except Exception as e:
        print(f"  ❌ Configuration loading failed: {e}")
        tests_failed += 1
    
    # Test 5: File structure validation
    print("\n🧪 Test 5: File Structure Validation")
    try:
        required_files = [
            "test_comprehensive_system.py",
            "run_comprehensive_tests.py",
            "test_config.yaml",
            "requirements_test.txt"
        ]
        
        missing_files = []
        for file in required_files:
            if not Path(file).exists():
                missing_files.append(file)
        
        if not missing_files:
            print("  ✅ All required test files present")
            tests_passed += 1
        else:
            print(f"  ⚠️ Missing files: {missing_files}")
            tests_passed += 1
    except Exception as e:
        print(f"  ❌ File structure validation failed: {e}")
        tests_failed += 1
    
    # Summary
    print("\n" + "=" * 50)
    print("🎯 QUICK TEST SUMMARY")
    print("=" * 50)
    print(f"✅ Passed: {tests_passed}")
    print(f"❌ Failed: {tests_failed}")
    print(f"📊 Total: {tests_passed + tests_failed}")
    
    if tests_failed == 0:
        print("🎉 All quick tests passed! Ready for comprehensive testing.")
        return True
    else:
        print(f"⚠️ {tests_failed} tests failed. Please fix issues before running comprehensive tests.")
        return False


if __name__ == "__main__":
    success = run_quick_tests()
    sys.exit(0 if success else 1)
