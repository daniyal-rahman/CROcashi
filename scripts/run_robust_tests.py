#!/usr/bin/env python3
"""
Robust Test Runner

This script runs all the new robust tests in sequence to validate the literature pipeline
according to the comprehensive testing requirements.
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def run_test(test_name, test_path):
    """Run a single test and return success status."""
    print(f"\n{'='*80}")
    print(f" 🚀 Running {test_name}")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    try:
        # Run the test
        result = subprocess.run([sys.executable, test_path], 
                              capture_output=True, text=True, timeout=300)
        
        duration = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✅ {test_name} PASSED in {duration:.2f}s")
            print("Output:")
            print(result.stdout)
            return True
        else:
            print(f"❌ {test_name} FAILED in {duration:.2f}s")
            print("Error output:")
            print(result.stderr)
            print("Standard output:")
            print(result.stdout)
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {test_name} TIMEOUT after 300s")
        return False
    except Exception as e:
        print(f"💥 {test_name} ERROR: {e}")
        return False

def main():
    """Run all robust tests."""
    print("🚀 Starting Robust Literature Pipeline Test Suite")
    print("This will run all comprehensive tests to validate the pipeline")
    
    # Define tests to run
    tests = [
        ("PubMed Query Builder Test", "tests/test_pubmed_query_builder.py"),
        ("LLM Evaluation Controlled Test", "tests/test_llm_evaluation_controlled.py"),
        ("Robust Literature Pipeline Test", "tests/test_literature_pipeline_robust.py")
    ]
    
    # Check if test files exist
    missing_tests = []
    for test_name, test_path in tests:
        if not Path(test_path).exists():
            missing_tests.append(test_path)
    
    if missing_tests:
        print(f"❌ Missing test files: {missing_tests}")
        print("Please ensure all test files are created before running.")
        sys.exit(1)
    
    # Run tests
    results = {}
    total_start_time = time.time()
    
    for test_name, test_path in tests:
        success = run_test(test_name, test_path)
        results[test_name] = success
        
        # Brief pause between tests
        time.sleep(1)
    
    # Summary
    total_duration = time.time() - total_start_time
    passed_tests = sum(1 for success in results.values() if success)
    total_tests = len(tests)
    
    print(f"\n{'='*80}")
    print(f" 🎯 TEST SUITE SUMMARY")
    print(f"{'='*80}")
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Total Duration: {total_duration:.2f}s")
    
    if passed_tests == total_tests:
        print("\n🎉 ALL TESTS PASSED!")
        print("The literature pipeline is robust and production-ready.")
        print("All comprehensive testing requirements have been met.")
        return 0
    else:
        print(f"\n💥 {total_tests - passed_tests} TESTS FAILED!")
        failed_tests = [name for name, success in results.items() if not success]
        print(f"Failed tests: {', '.join(failed_tests)}")
        print("Please review the failures and fix the issues.")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Test suite interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test suite failed with unexpected error: {e}")
        sys.exit(1)
