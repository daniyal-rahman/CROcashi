#!/usr/bin/env python3
"""
Quick PMC2978916 Test Runner

Provides a concise summary of the PMC2978916 end-to-end test results.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tests'))

from test_pmc2978916_e2e import PMC2978916E2ETest


def main():
    """Run the test and provide a quick summary."""
    
    print("🧪 Running PMC2978916 End-to-End Test...")
    print("=" * 60)
    
    # Create output directory
    output_dir = Path("test_outputs/pmc2978916_quick")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Run the test
    test_runner = PMC2978916E2ETest(str(output_dir))
    results = test_runner.run_full_test()
    
    # Quick summary
    print(f"\n📊 QUICK SUMMARY:")
    print(f"   Overall Success: {'✅ PASSED' if results['success'] else '❌ FAILED'}")
    print(f"   Errors: {len(results.get('errors', []))}")
    print(f"   Warnings: {len(results.get('warnings', []))}")
    
    # Validation results
    validation_results = results.get('validation_results', {})
    print(f"   Validation Checks: {len(validation_results)}")
    
    for validation_name, validation_data in validation_results.items():
        errors = len(validation_data.get('errors', []))
        warnings = len(validation_data.get('warnings', []))
        status = "✅" if errors == 0 else "⚠️" if warnings > 0 else "❌"
        print(f"   - {validation_name}: {status} ({errors} errors, {warnings} warnings)")
    
    print(f"\n📁 Output Directory: {output_dir}")
    print(f"📄 Generated Files:")
    for file_path in output_dir.glob("*.json"):
        file_size = file_path.stat().st_size
        print(f"   - {file_path.name} ({file_size} bytes)")
    
    print(f"\n🔍 For detailed analysis, see: {output_dir}/DEBUG_SUMMARY.md")
    
    # Exit with appropriate code
    if results.get('success', False):
        print("\n🎉 Test completed successfully!")
        sys.exit(0)
    else:
        print("\n🔧 Test completed with issues - check artifacts for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
