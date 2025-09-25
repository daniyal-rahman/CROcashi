#!/usr/bin/env python3
"""
Runner for the Content Retrieval Fallback Chain Test.
"""

import asyncio
from content_retrieval_fallback_test import ContentRetrievalFallbackTest


async def main():
    """Run the content retrieval fallback test."""
    print("🚀 Starting Content Retrieval Fallback Chain Test")
    print("=" * 60)
    
    try:
        test = ContentRetrievalFallbackTest()
        await test.run_test()
        print("✅ Test completed successfully!")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
