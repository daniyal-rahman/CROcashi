#!/usr/bin/env python3
"""
Runner for Comprehensive Cassava Pipeline Test

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
from tests.scripts.comprehensive_cassava_pipeline_test import main
import asyncio

if __name__ == "__main__":
    print("🧪 Running Comprehensive Cassava Pipeline Test")
    print("=" * 60)
    print("This test will:")
    print("• Clear the test database completely")
    print("• Seed real Cassava trial data")
    print("• Test PubMed literature processing")
    print("• Test study card generation with LLM workers")
    print("• Test orchestrator integration")
    print("• Validate data integrity")
    print("=" * 60)
    
    asyncio.run(main())
