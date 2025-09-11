#!/usr/bin/env python3
"""
Test runner for the Cassava CT.gov + PubMed ingestion test.

This script provides a simple way to run the test with proper environment setup.
"""

import os
import sys
from pathlib import Path

def setup_environment():
    """Setup environment variables for testing."""
    # Set test mode
    os.environ['TEST_MODE'] = 'true'
    os.environ['LOG_LEVEL'] = 'INFO'
    
    # Set default database if not already set
    if 'PSQL_DSN' not in os.environ:
        os.environ['PSQL_DSN'] = 'postgresql://ncfd:ncfd@localhost:5433/ncfd'
        print("🔧 Using default test database: postgresql://ncfd:ncfd@localhost:5433/ncfd")
    
    # Set default OpenAI key if not set
    if 'OPENAI_API_KEY' not in os.environ:
        os.environ['OPENAI_API_KEY'] = 'test-key-for-testing'
        print("🔧 Using test OpenAI key (set OPENAI_API_KEY for real API calls)")
    
    # Set default PubMed email if not set
    if 'PUBMED_EMAIL' not in os.environ:
        os.environ['PUBMED_EMAIL'] = 'test@example.com'
        print("🔧 Using test PubMed email (set PUBMED_EMAIL for real API calls)")

def main():
    """Main test runner."""
    print("🧪 Cassava CT.gov + PubMed Ingestion Test Runner")
    print("=" * 60)
    
    # Setup environment
    setup_environment()
    
    # Add project root to path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root / "src"))
    
    try:
        # Import and run the test
        from tests.scripts.cassava_ctgov_pubmed_test import main as run_test
        run_test()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running from the project root directory")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
