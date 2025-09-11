#!/usr/bin/env python3
"""
Simple runner for the Cassava CT.gov + PubMed test.

This script sets up the environment and runs the comprehensive test.
"""

import os
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Set up environment variables for testing
os.environ.setdefault('TEST_MODE', 'true')
os.environ.setdefault('LOG_LEVEL', 'INFO')

# Import and run the test
from tests.scripts.cassava_ctgov_pubmed_test import main

if __name__ == "__main__":
    print("🧪 Running Cassava CT.gov + PubMed Ingestion Test")
    print("=" * 60)
    main()
