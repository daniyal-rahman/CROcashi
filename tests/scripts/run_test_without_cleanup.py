#!/usr/bin/env python3
"""
Run Comprehensive Test Without Cleanup

This script runs the comprehensive test but skips the database cleanup
so we can inspect the document counts afterward.

Usage:
    python tests/scripts/run_test_without_cleanup.py
"""

import sys
from pathlib import Path

# Add the src directory to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "tests"))

# Setup test environment before importing modules
from utils.env_loader import setup_test_environment
setup_test_environment(project_root)

import asyncio
from comprehensive_cassava_pipeline_test import ComprehensiveCassavaTest


class ComprehensiveCassavaTestNoCleanup(ComprehensiveCassavaTest):
    """Comprehensive test that skips database cleanup."""
    
    async def run_comprehensive_test(self):
        """Run the comprehensive pipeline test without cleanup."""
        print("🧪 Starting Comprehensive Cassava Pipeline Test (No Cleanup)")
        print("=" * 80)
        
        try:
            # Phase 1: Database Setup
            await self._setup_database()
            
            # Phase 2: CT.gov Trial Seeding
            await self._seed_ctgov_trials()
            
            # Phase 3: Orchestrator Integration (includes PubMed + Study Card processing)
            await self._test_orchestrator()
            
            # Phase 6: Validation and Reporting
            await self._validate_results()
            
            # Final reporting
            self._generate_final_report()
            
            print("\n" + "="*80)
            print("✅ Test completed successfully! Database has NOT been cleaned up.")
            print("   You can now run: python tests/scripts/check_document_counts.py")
            print("="*80)
            
        except Exception as e:
            print(f"❌ Test failed: {str(e)}")
            self.results["errors"].append(f"Test execution failed: {str(e)}")
            raise
        # Note: No cleanup in finally block


async def main():
    """Main test function."""
    test = ComprehensiveCassavaTestNoCleanup()
    await test.run_comprehensive_test()


if __name__ == "__main__":
    asyncio.run(main())
