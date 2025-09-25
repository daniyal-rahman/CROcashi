#!/usr/bin/env python3
"""
Runner for the PMC Content Fix Test.
"""

import asyncio
from pmc_content_fix_test import PMCContentFixTest


async def main():
    """Run the PMC content fix test."""
    print("🚀 Starting PMC Content Retrieval Fix Test")
    print("=" * 60)
    
    try:
        test = PMCContentFixTest()
        await test.run_test()
        print("✅ PMC fix test completed successfully!")
    except Exception as e:
        print(f"❌ PMC fix test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
