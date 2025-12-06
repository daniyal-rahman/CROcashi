#!/usr/bin/env python
"""
Simple test runner for backtesting tests.
"""
import sys
import pytest

if __name__ == "__main__":
    exit_code = pytest.main([__file__.replace("run_tests.py", "test_catalyst_extractor.py"), "-v", "--tb=short"])
    sys.exit(exit_code)
