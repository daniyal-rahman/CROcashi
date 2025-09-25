#!/usr/bin/env python3
"""
Runner for the Enhanced Content Retrieval Fallback Chain Test.
"""

import asyncio
from enhanced_content_retrieval_test import EnhancedContentRetrievalTest


async def main():
    """Run the enhanced content retrieval fallback test."""
    print("🚀 Starting Enhanced Content Retrieval Fallback Chain Test")
    print("=" * 70)
    
    try:
        test = EnhancedContentRetrievalTest()
        await test.run_test()
        print("✅ Enhanced test completed successfully!")
    except Exception as e:
        print(f"❌ Enhanced test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
