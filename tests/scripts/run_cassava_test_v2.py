#!/usr/bin/env python3
"""
Runner script for Comprehensive Cassava Pipeline Test V2

This script provides a simple way to run the Cassava test with proper
environment setup and error handling.

Usage:
    python tests/scripts/run_cassava_test_v2.py
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "tests"))

# Import the test
from comprehensive_cassava_pipeline_test_v2 import ComprehensiveCassavaTestV2


async def main():
    """Run the Cassava test V2."""
    print("🚀 Starting Comprehensive Cassava Pipeline Test V2")
    print("=" * 60)
    
    try:
        test = ComprehensiveCassavaTestV2()
        await test.run_comprehensive_test()
        print("\n✅ Test completed successfully!")
        return 0
        
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        return 1
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
