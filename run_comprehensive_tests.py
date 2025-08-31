#!/usr/bin/env python3
"""
Comprehensive Test Runner for Study Card System

This script runs the complete test suite with various configurations and generates
detailed reports. It can be used for:
- Development testing
- CI/CD pipeline testing
- Performance benchmarking
- Regression testing
"""

import sys
import os
import argparse
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


class TestRunner:
    """Comprehensive test runner for the Study Card system."""
    
    def __init__(self, config_file: str = "test_config.yaml"):
        """Initialize the test runner."""
        self.config_file = config_file
        self.config = self._load_config()
        self.results_dir = Path(self.config.get("output", {}).get("results_dir", "test_results"))
        self.results_dir.mkdir(exist_ok=True)
        
        # Test results storage
        self.test_results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": self.config,
            "tests": {},
            "summary": {},
            "performance": {},
            "artifacts": {}
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """Load test configuration."""
        try:
            import yaml
            with open(self.config_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load config file {self.config_file}: {e}")
            return {}
    
    def run_basic_tests(self) -> bool:
        """Run basic functionality tests."""
        print("🧪 Running Basic Functionality Tests...")
        
        try:
            # Import and test basic components
            from ncfd.extract.workers import BaseWorker
            from ncfd.extract.models import EvidenceSpan
            
            # Test basic imports
            print("  ✅ Basic imports successful")
            
            # Test model creation
            span = EvidenceSpan(
                doc_id="test:123",
                quote="Test quote",
                section="Methods"
            )
            print("  ✅ Model creation successful")
            
            return True
            
        except Exception as e:
            print(f"  ❌ Basic tests failed: {e}")
            return False
    
    def run_unit_tests(self) -> Dict[str, Any]:
        """Run unit tests using pytest."""
        print("🔬 Running Unit Tests...")
        
        test_results = {
            "success": False,
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": [],
            "coverage": 0.0
        }
        
        try:
            # Run pytest with coverage
            cmd = [
                "python", "-m", "pytest",
                "test_comprehensive_system.py",
                "--tb=short",
                "--cov=src/ncfd",
                "--cov-report=html:test_results/coverage",
                "--cov-report=json:test_results/coverage.json",
                "--cov-report=term-missing",
                "-v"
            ]
            
            print(f"  Running: {' '.join(cmd)}")
            
            # Run the tests
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            end_time = time.time()
            
            # Parse results
            test_results["execution_time"] = end_time - start_time
            test_results["return_code"] = result.returncode
            
            if result.returncode == 0:
                test_results["success"] = True
                print("  ✅ All unit tests passed")
            else:
                print(f"  ❌ Unit tests failed with return code {result.returncode}")
                test_results["errors"].append(result.stderr)
            
            # Parse test output for counts
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if "passed" in line and "failed" in line:
                    # Extract test counts
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "passed":
                            test_results["passed"] = int(parts[i-1])
                        elif part == "failed":
                            test_results["failed"] = int(parts[i-1])
                    test_results["total_tests"] = test_results["passed"] + test_results["failed"]
                    break
            
            print(f"  📊 Results: {test_results['passed']} passed, {test_results['failed']} failed")
            
        except subprocess.TimeoutExpired:
            test_results["errors"].append("Tests timed out after 5 minutes")
            print("  ⏰ Tests timed out")
        except Exception as e:
            test_results["errors"].append(str(e))
            print(f"  ❌ Error running tests: {e}")
        
        return test_results
    
    def run_performance_tests(self) -> Dict[str, Any]:
        """Run performance and resource tests."""
        print("⚡ Running Performance Tests...")
        
        performance_results = {
            "memory_usage": {},
            "execution_times": {},
            "resource_limits": {}
        }
        
        try:
            import psutil
            process = psutil.Process()
            
            # Measure memory usage
            memory_info = process.memory_info()
            performance_results["memory_usage"] = {
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "percent": process.memory_percent()
            }
            
            # Check against limits
            max_memory = self.config.get("test_config", {}).get("max_memory_usage", 1024)
            if performance_results["memory_usage"]["rss_mb"] > max_memory:
                performance_results["resource_limits"]["memory_exceeded"] = True
                print(f"  ⚠️ Memory usage {performance_results['memory_usage']['rss_mb']:.1f}MB exceeds limit {max_memory}MB")
            else:
                print(f"  ✅ Memory usage {performance_results['memory_usage']['rss_mb']:.1f}MB within limits")
            
            # Measure CPU usage
            cpu_percent = process.cpu_percent(interval=1)
            performance_results["cpu_usage"] = cpu_percent
            print(f"  📊 CPU usage: {cpu_percent:.1f}%")
            
        except Exception as e:
            print(f"  ❌ Performance testing failed: {e}")
            performance_results["errors"] = [str(e)]
        
        return performance_results
    
    def run_integration_tests(self) -> Dict[str, Any]:
        """Run integration tests."""
        print("🔗 Running Integration Tests...")
        
        integration_results = {
            "success": False,
            "components_tested": [],
            "errors": []
        }
        
        try:
            # Test component integration
            from ncfd.extract.orchestrate import LateFusionOrchestrator
            from ncfd.extract.workers.llm import MethodAuditor
            from ncfd.extract.workers.deterministic import GateValidator
            
            # Test orchestrator creation
            orchestrator = LateFusionOrchestrator()
            integration_results["components_tested"].append("LateFusionOrchestrator")
            
            # Test worker creation
            method_auditor = MethodAuditor()
            integration_results["components_tested"].append("MethodAuditor")
            
            gate_validator = GateValidator()
            integration_results["components_tested"].append("GateValidator")
            
            integration_results["success"] = True
            print(f"  ✅ Integration tests passed for {len(integration_results['components_tested'])} components")
            
        except Exception as e:
            integration_results["errors"].append(str(e))
            print(f"  ❌ Integration tests failed: {e}")
        
        return integration_results
    
    def run_validation_tests(self) -> Dict[str, Any]:
        """Run validation and schema tests."""
        print("✅ Running Validation Tests...")
        
        validation_results = {
            "schemas_validated": [],
            "validation_rules_tested": [],
            "errors": []
        }
        
        try:
            # Test schema validation
            from ncfd.extract.schemas.base import BASE_SCHEMA
            from ncfd.extract.validators import validate_artifacts
            
            # Test base schema
            validation_results["schemas_validated"].append("BASE_SCHEMA")
            
            # Test validation function
            mock_artifacts = {
                "method_card": {},
                "results_factsheet": {},
                "claims": []
            }
            
            validation_result = validate_artifacts(mock_artifacts)
            validation_results["validation_rules_tested"].append("validate_artifacts")
            
            print(f"  ✅ Validation tests passed for {len(validation_results['schemas_validated'])} schemas")
            
        except Exception as e:
            validation_results["errors"].append(str(e))
            print(f"  ❌ Validation tests failed: {e}")
        
        return validation_results
    
    def generate_report(self) -> str:
        """Generate comprehensive test report."""
        print("📊 Generating Test Report...")
        
        # Calculate summary statistics
        total_tests = 0
        total_passed = 0
        total_failed = 0
        
        for test_type, results in self.test_results["tests"].items():
            if isinstance(results, dict):
                if "total_tests" in results:
                    total_tests += results.get("total_tests", 0)
                    total_passed += results.get("passed", 0)
                    total_failed += results.get("failed", 0)
        
        self.test_results["summary"] = {
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "success_rate": (total_passed / total_tests * 100) if total_tests > 0 else 0
        }
        
        # Generate HTML report
        html_report = self._generate_html_report()
        html_file = self.results_dir / "test_report.html"
        with open(html_file, 'w') as f:
            f.write(html_report)
        
        # Generate JSON report
        json_file = self.results_dir / "test_results.json"
        with open(json_file, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)
        
        print(f"  📄 HTML report: {html_file}")
        print(f"  📄 JSON report: {json_file}")
        
        return str(html_file)
    
    def _generate_html_report(self) -> str:
        """Generate HTML test report."""
        summary = self.test_results["summary"]
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Study Card System Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .summary {{ background-color: #e8f5e8; padding: 20px; border-radius: 5px; margin: 20px 0; }}
        .test-section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .success {{ color: green; }}
        .error {{ color: red; }}
        .warning {{ color: orange; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Study Card System Comprehensive Test Report</h1>
        <p><strong>Generated:</strong> {self.test_results['timestamp']}</p>
        <p><strong>Configuration:</strong> {self.config_file}</p>
    </div>
    
    <div class="summary">
        <h2>Test Summary</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Total Tests</td><td>{summary['total_tests']}</td></tr>
            <tr><td>Passed</td><td class="success">{summary['total_passed']}</td></tr>
            <tr><td>Failed</td><td class="error">{summary['total_failed']}</td></tr>
            <tr><td>Success Rate</td><td>{summary['success_rate']:.1f}%</td></tr>
        </table>
    </div>
"""
        
        # Add test sections
        for test_type, results in self.test_results["tests"].items():
            if isinstance(results, dict):
                status_class = "success" if results.get("success", False) else "error"
                status_text = "✅ PASSED" if results.get("success", False) else "❌ FAILED"
                
                html += f"""
    <div class="test-section">
        <h3>{test_type.replace('_', ' ').title()}</h3>
        <p><strong>Status:</strong> <span class="{status_class}">{status_text}</span></p>
"""
                
                if "execution_time" in results:
                    html += f"        <p><strong>Execution Time:</strong> {results['execution_time']:.2f}s</p>"
                
                if "errors" in results and results["errors"]:
                    html += f"        <p><strong>Errors:</strong></p><ul>"
                    for error in results["errors"]:
                        html += f"            <li class='error'>{error}</li>"
                    html += "        </ul>"
                
                html += "    </div>"
        
        # Add performance section
        if self.test_results["performance"]:
            html += """
    <div class="test-section">
        <h3>Performance Metrics</h3>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
"""
            
            perf = self.test_results["performance"]
            if "memory_usage" in perf:
                mem = perf["memory_usage"]
                html += f"            <tr><td>Memory Usage (RSS)</td><td>{mem.get('rss_mb', 0):.1f} MB</td></tr>"
                html += f"            <tr><td>Memory Usage (VMS)</td><td>{mem.get('vms_mb', 0):.1f} MB</td></tr>"
                html += f"            <tr><td>Memory Percent</td><td>{mem.get('percent', 0):.1f}%</td></tr>"
            
            if "cpu_usage" in perf:
                html += f"            <tr><td>CPU Usage</td><td>{perf['cpu_usage']:.1f}%</td></tr>"
            
            html += "        </table>    </div>"
        
        html += """
</body>
</html>
"""
        
        return html
    
    def run_all_tests(self) -> bool:
        """Run all test categories."""
        print("🚀 Starting Comprehensive Test Suite...")
        print("=" * 60)
        
        start_time = time.time()
        
        # Run basic tests
        basic_success = self.run_basic_tests()
        self.test_results["tests"]["basic_tests"] = {"success": basic_success}
        
        if not basic_success:
            print("❌ Basic tests failed, stopping test suite")
            return False
        
        # Run unit tests
        unit_results = self.run_unit_tests()
        self.test_results["tests"]["unit_tests"] = unit_results
        
        # Run integration tests
        integration_results = self.run_integration_tests()
        self.test_results["tests"]["integration_tests"] = integration_results
        
        # Run validation tests
        validation_results = self.run_validation_tests()
        self.test_results["tests"]["validation_tests"] = validation_results
        
        # Run performance tests
        performance_results = self.run_performance_tests()
        self.test_results["performance"] = performance_results
        
        # Generate report
        report_file = self.generate_report()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Print summary
        print("\n" + "=" * 60)
        print("🎯 TEST SUITE COMPLETED")
        print("=" * 60)
        
        summary = self.test_results["summary"]
        print(f"📊 Total Tests: {summary['total_tests']}")
        print(f"✅ Passed: {summary['total_passed']}")
        print(f"❌ Failed: {summary['total_failed']}")
        print(f"🎯 Success Rate: {summary['success_rate']:.1f}%")
        print(f"⏱️ Total Time: {total_time:.2f}s")
        print(f"📄 Report: {report_file}")
        
        return summary['total_failed'] == 0


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(description="Run comprehensive tests for Study Card system")
    parser.add_argument("--config", "-c", default="test_config.yaml", help="Configuration file path")
    parser.add_argument("--quick", "-q", action="store_true", help="Run quick tests only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--output-dir", "-o", help="Output directory for results")
    
    args = parser.parse_args()
    
    # Create test runner
    runner = TestRunner(args.config)
    
    if args.output_dir:
        runner.results_dir = Path(args.output_dir)
        runner.results_dir.mkdir(exist_ok=True)
    
    # Run tests
    success = runner.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
