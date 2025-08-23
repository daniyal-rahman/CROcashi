#!/usr/bin/env python3
"""
Comprehensive Test Runner for CROcashi.

This script provides a unified interface for running all tests, specific test categories,
or individual test files with proper reporting and coverage analysis.
"""

import argparse
import sys
import os
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any
import json

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestRunner:
    """Comprehensive test runner for CROcashi."""
    
    def __init__(self, verbose: bool = False):
        """Initialize the test runner."""
        self.verbose = verbose
        self.project_root = Path(__file__).parent.parent
        self.tests_dir = self.project_root / "tests"
        self.src_dir = self.project_root / "src"
        
        # Test categories and their corresponding test files
        self.test_categories = {
            "all": "All tests",
            "unit": "Unit tests only",
            "integration": "Integration tests only",
            "data_quality": "Data quality framework tests",
            "monitoring": "Pipeline monitoring tests",
            "ingestion": "Data ingestion tests",
            "orchestration": "Pipeline orchestration tests",
            "quick": "Quick smoke tests"
        }
        
        # Test file mappings
        self.test_files = {
            "data_quality": ["tests/test_data_quality.py"],
            "monitoring": ["tests/test_pipeline_monitor.py"],
            "ingestion": [
                "tests/test_ctgov_client.py",
                "tests/test_sec_filings.py"
            ],
            "orchestration": ["tests/test_unified_orchestrator.py"]
        }
        
        # Results storage
        self.test_results = {}
        self.start_time = None
        self.end_time = None
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
    
    def check_dependencies(self) -> bool:
        """Check if required dependencies are available."""
        try:
            import pytest
            self.log("✓ pytest is available")
        except ImportError:
            self.log("✗ pytest is not available. Please install with: pip install pytest", "ERROR")
            return False
        
        try:
            import psutil
            self.log("✓ psutil is available")
        except ImportError:
            self.log("✗ psutil is not available. Please install with: pip install psutil", "ERROR")
            return False
        
        try:
            import requests
            self.log("✓ requests is available")
        except ImportError:
            self.log("✗ requests is not available. Please install with: pip install requests", "ERROR")
            return False
        
        return True
    
    def discover_tests(self) -> List[str]:
        """Discover all available test files."""
        test_files = []
        
        if self.tests_dir.exists():
            for test_file in self.tests_dir.glob("test_*.py"):
                test_files.append(str(test_file))
        
        return sorted(test_files)
    
    def run_pytest(self, test_paths: List[str], additional_args: List[str] = None) -> Dict[str, Any]:
        """Run pytest with specified test paths."""
        if additional_args is None:
            additional_args = []
        
        # Build pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            "--tb=short",  # Short traceback format
            "--strict-markers",  # Strict marker checking
            "--disable-warnings",  # Disable warnings for cleaner output
            "--json-report",  # Generate JSON report
            "--json-report-file=none"  # Don't write to file, capture output
        ]
        
        # Add test paths
        cmd.extend(test_paths)
        
        # Add additional arguments
        cmd.extend(additional_args)
        
        if self.verbose:
            cmd.append("-v")
        
        self.log(f"Running pytest command: {' '.join(cmd)}")
        
        try:
            # Run pytest
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=300  # 5 minute timeout
            )
            
            # Parse results
            test_result = {
                "return_code": result.return_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.return_code == 0
            }
            
            # Try to extract test summary from output
            if "passed" in result.stdout or "failed" in result.stdout:
                lines = result.stdout.split('\n')
                for line in lines:
                    if "passed" in line and "failed" in line:
                        test_result["summary"] = line.strip()
                        break
            
            return test_result
            
        except subprocess.TimeoutExpired:
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": "Test execution timed out after 5 minutes",
                "success": False,
                "error": "timeout"
            }
        except Exception as e:
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False,
                "error": "exception"
            }
    
    def run_category_tests(self, category: str) -> Dict[str, Any]:
        """Run tests for a specific category."""
        if category not in self.test_categories:
            return {
                "success": False,
                "error": f"Unknown test category: {category}"
            }
        
        if category == "all":
            # Run all discovered tests
            test_files = self.discover_tests()
        elif category == "quick":
            # Run a subset of tests for quick validation
            test_files = [
                "tests/test_data_quality.py",
                "tests/test_pipeline_monitor.py"
            ]
        else:
            # Run tests for specific category
            test_files = self.test_files.get(category, [])
        
        if not test_files:
            return {
                "success": False,
                "error": f"No test files found for category: {category}"
            }
        
        self.log(f"Running {category} tests: {len(test_files)} test files")
        
        # Run tests
        result = self.run_pytest(test_files)
        
        # Store result
        self.test_results[category] = result
        
        return result
    
    def run_specific_tests(self, test_files: List[str]) -> Dict[str, Any]:
        """Run specific test files."""
        # Validate test files exist
        valid_files = []
        for test_file in test_files:
            test_path = Path(test_file)
            if test_path.exists():
                valid_files.append(test_file)
            else:
                self.log(f"Warning: Test file not found: {test_file}", "WARNING")
        
        if not valid_files:
            return {
                "success": False,
                "error": "No valid test files found"
            }
        
        self.log(f"Running specific tests: {len(valid_files)} test files")
        
        # Run tests
        result = self.run_pytest(valid_files)
        
        # Store result
        self.test_results["specific"] = result
        
        return result
    
    def run_coverage_tests(self, test_paths: List[str] = None) -> Dict[str, Any]:
        """Run tests with coverage analysis."""
        if test_paths is None:
            test_paths = self.discover_tests()
        
        self.log("Running tests with coverage analysis")
        
        # Additional arguments for coverage
        coverage_args = [
            "--cov=src",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-report=json:coverage.json"
        ]
        
        # Run tests with coverage
        result = self.run_pytest(test_paths, coverage_args)
        
        # Store result
        self.test_results["coverage"] = result
        
        return result
    
    def generate_report(self) -> str:
        """Generate a comprehensive test report."""
        if not self.test_results:
            return "No test results available"
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("CROcashi Test Execution Report")
        report_lines.append("=" * 80)
        
        # Execution time
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            report_lines.append(f"Total Execution Time: {duration:.2f} seconds")
        
        report_lines.append("")
        
        # Results summary
        total_categories = len(self.test_results)
        successful_categories = sum(1 for r in self.test_results.values() if r.get("success", False))
        
        report_lines.append(f"Test Categories: {total_categories}")
        report_lines.append(f"Successful: {successful_categories}")
        report_lines.append(f"Failed: {total_categories - successful_categories}")
        report_lines.append("")
        
        # Detailed results
        for category, result in self.test_results.items():
            report_lines.append(f"Category: {category}")
            report_lines.append("-" * 40)
            
            if result.get("success", False):
                report_lines.append("Status: ✓ PASSED")
                if "summary" in result:
                    report_lines.append(f"Summary: {result['summary']}")
            else:
                report_lines.append("Status: ✗ FAILED")
                if "error" in result:
                    report_lines.append(f"Error: {result['error']}")
                if result.get("stderr"):
                    report_lines.append(f"Details: {result['stderr'][:200]}...")
            
            report_lines.append("")
        
        # Recommendations
        if successful_categories < total_categories:
            report_lines.append("Recommendations:")
            report_lines.append("- Review failed test categories")
            report_lines.append("- Check test dependencies and environment")
            report_lines.append("- Run individual test files for detailed debugging")
        
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def save_report(self, report: str, filename: str = None):
        """Save the test report to a file."""
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"test_report_{timestamp}.txt"
        
        report_path = self.project_root / filename
        
        try:
            with open(report_path, 'w') as f:
                f.write(report)
            self.log(f"Test report saved to: {report_path}")
        except Exception as e:
            self.log(f"Failed to save test report: {e}", "ERROR")
    
    def run(self, category: str = None, test_files: List[str] = None, 
            coverage: bool = False, save_report: bool = False) -> bool:
        """Run the main test execution."""
        self.start_time = time.time()
        
        self.log("Starting CROcashi test execution")
        
        # Check dependencies
        if not self.check_dependencies():
            self.log("Dependency check failed. Exiting.", "ERROR")
            return False
        
        # Determine what to run
        if test_files:
            # Run specific test files
            result = self.run_specific_tests(test_files)
        elif category:
            # Run category tests
            result = self.run_category_tests(category)
        else:
            # Default to running all tests
            result = self.run_category_tests("all")
        
        # Run coverage if requested
        if coverage:
            self.run_coverage_tests()
        
        self.end_time = time.time()
        
        # Generate and display report
        report = self.generate_report()
        print("\n" + report)
        
        # Save report if requested
        if save_report:
            self.save_report(report)
        
        # Return overall success
        return all(r.get("success", False) for r in self.test_results.values())


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(
        description="CROcashi Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all tests
  python scripts/run_tests.py
  
  # Run specific category
  python scripts/run_tests.py --category data_quality
  
  # Run specific test files
  python scripts/run_tests.py --test-files tests/test_data_quality.py
  
  # Run with coverage
  python scripts/run_tests.py --coverage
  
  # Run quick tests and save report
  python scripts/run_tests.py --category quick --save-report
        """
    )
    
    parser.add_argument(
        "--category", "-c",
        choices=["all", "unit", "integration", "data_quality", "monitoring", 
                "ingestion", "orchestration", "quick"],
        help="Test category to run"
    )
    
    parser.add_argument(
        "--test-files", "-t",
        nargs="+",
        help="Specific test files to run"
    )
    
    parser.add_argument(
        "--coverage", "-v",
        action="store_true",
        help="Run tests with coverage analysis"
    )
    
    parser.add_argument(
        "--save-report", "-s",
        action="store_true",
        help="Save test report to file"
    )
    
    parser.add_argument(
        "--verbose", "-V",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="List available test categories and exit"
    )
    
    args = parser.parse_args()
    
    # Create test runner
    runner = TestRunner(verbose=args.verbose)
    
    # List categories if requested
    if args.list_categories:
        print("Available test categories:")
        for category, description in runner.test_categories.items():
            print(f"  {category}: {description}")
        return 0
    
    # Run tests
    success = runner.run(
        category=args.category,
        test_files=args.test_files,
        coverage=args.coverage,
        save_report=args.save_report
    )
    
    # Exit with appropriate code
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
