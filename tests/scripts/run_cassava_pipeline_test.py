#!/usr/bin/env python3
"""
Runner for the consolidated Cassava pipeline test.
"""

import asyncio
from cassava_pipeline_test import CassavaPipelineTest


async def main():
    """Run the consolidated Cassava pipeline test."""
    print("🚀 Starting Consolidated Cassava Pipeline Test")
    print("=" * 60)
    
    try:
        test = CassavaPipelineTest()
        await test.run_test()
        print("✅ Test completed successfully!")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
