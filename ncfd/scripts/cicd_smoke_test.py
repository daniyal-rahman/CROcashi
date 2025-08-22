#!/opt/homebrew/Caskroom/miniconda/base/bin/python3.12
"""
CI/CD Pipeline Smoke Test for NCFD Phase 9
Tests the CI/CD configuration and deployment infrastructure
"""

import os
import sys
import yaml
import subprocess
import time
from typing import Dict, List, Any, Tuple

class CICDSmokeTest:
    def __init__(self):
        self.results = {}
        self.start_time = time.time()
        
    def test_github_actions_config(self) -> Tuple[bool, str]:
        """Test GitHub Actions workflow configuration"""
        try:
            workflow_file = '.github/workflows/ci-cd.yml'
            if not os.path.exists(workflow_file):
                return False, f"GitHub Actions workflow not found: {workflow_file}"
            
            # Validate YAML syntax
            with open(workflow_file, 'r') as f:
                workflow_config = yaml.safe_load(f)
            
            # Check required sections (handle YAML parsing quirk where 'on' becomes True)
            required_sections = ['name', 'jobs']
            missing_sections = []
            for section in required_sections:
                if section not in workflow_config:
                    missing_sections.append(section)
            
            # Check for 'on' section (either as 'on' or True)
            has_on_section = 'on' in workflow_config or True in workflow_config
            if not has_on_section:
                missing_sections.append('on')
            
            if missing_sections:
                return False, f"Workflow missing required sections: {', '.join(missing_sections)}"
            
            # Check if jobs exist
            jobs = workflow_config.get('jobs', {})
            if not jobs:
                return False, "No jobs defined in workflow"
            
            # Check for required jobs (at least one job should exist)
            if not jobs:
                return False, "No jobs defined in workflow"
            
            # Check that we have at least one job with a reasonable name
            job_names = list(jobs.keys())
            if not any('test' in name.lower() or 'build' in name.lower() or 'deploy' in name.lower() for name in job_names):
                return False, f"Workflow should have test, build, or deploy jobs, found: {', '.join(job_names)}"
            
            return True, f"GitHub Actions workflow valid with {len(jobs)} jobs"
            
        except Exception as e:
            return False, f"GitHub Actions config test failed: {str(e)}"
    
    def test_pre_commit_config(self) -> Tuple[bool, str]:
        """Test pre-commit configuration"""
        try:
            precommit_file = '.pre-commit-config.yaml'
            if not os.path.exists(precommit_file):
                return False, f"Pre-commit config not found: {precommit_file}"
            
            # Validate YAML syntax
            with open(precommit_file, 'r') as f:
                precommit_config = yaml.safe_load(f)
            
            # Check if repos are defined
            repos = precommit_config.get('repos', [])
            if not repos:
                return False, "No repositories defined in pre-commit config"
            
            # Check for required hooks
            required_hooks = ['black', 'isort', 'flake8']
            found_hooks = []
            for repo in repos:
                for hook in repo.get('hooks', []):
                    found_hooks.append(hook.get('id', ''))
            
            missing_hooks = []
            for hook in required_hooks:
                if hook not in found_hooks:
                    missing_hooks.append(hook)
            
            if missing_hooks:
                return False, f"Pre-commit missing required hooks: {', '.join(missing_hooks)}"
            
            return True, f"Pre-commit config valid with {len(repos)} repositories"
            
        except Exception as e:
            return False, f"Pre-commit config test failed: {str(e)}"
    
    def test_deployment_script(self) -> Tuple[bool, str]:
        """Test deployment script configuration"""
        try:
            deploy_script = 'scripts/deploy.sh'
            if not os.path.exists(deploy_script):
                return False, f"Deployment script not found: {deploy_script}"
            
            # Check if script is executable
            if not os.access(deploy_script, os.X_OK):
                return False, "Deployment script is not executable"
            
            # Check script syntax
            result = subprocess.run(
                ['bash', '-n', deploy_script],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode != 0:
                return False, f"Deployment script syntax error: {result.stderr}"
            
            # Check for required functions
            with open(deploy_script, 'r') as f:
                script_content = f.read()
            
            required_functions = ['check_prerequisites', 'deploy_new_version', 'rollback']
            missing_functions = []
            for func in required_functions:
                if func not in script_content:
                    missing_functions.append(func)
            
            if missing_functions:
                return False, f"Deployment script missing required functions: {', '.join(missing_functions)}"
            
            return True, "Deployment script valid and executable"
            
        except Exception as e:
            return False, f"Deployment script test failed: {str(e)}"
    
    def test_docker_configs(self) -> Tuple[bool, str]:
        """Test Docker configuration files"""
        try:
            results = []
            
            # Check production Docker Compose
            if os.path.exists('docker-compose.prod.yml'):
                results.append("Production compose: Found")
            else:
                results.append("Production compose: Missing")
            
            # Check production Dockerfile
            if os.path.exists('Dockerfile.prod'):
                results.append("Production Dockerfile: Found")
            else:
                results.append("Production Dockerfile: Missing")
            
            # Check if all required files exist
            required_files = ['docker-compose.prod.yml', 'Dockerfile.prod']
            missing_files = []
            for file in required_files:
                if not os.path.exists(file):
                    missing_files.append(file)
            
            if missing_files:
                return False, f"Docker configs missing: {', '.join(missing_files)}"
            
            return True, f"Docker configurations: {'; '.join(results)}"
            
        except Exception as e:
            return False, f"Docker configs test failed: {str(e)}"
    
    def test_environment_configs(self) -> Tuple[bool, str]:
        """Test environment configuration files"""
        try:
            results = []
            
            # Check environment files
            env_files = ['.env.prod', 'env.prod.dev', 'config/config.prod.yaml']
            found_files = []
            missing_files = []
            
            for env_file in env_files:
                if os.path.exists(env_file):
                    found_files.append(env_file)
                else:
                    missing_files.append(env_file)
            
            if found_files:
                results.append(f"Found: {', '.join(found_files)}")
            
            if missing_files:
                results.append(f"Missing: {', '.join(missing_files)}")
            
            # At least one environment config should exist
            if not found_files:
                return False, "No environment configuration files found"
            
            return True, f"Environment configs: {'; '.join(results)}"
            
        except Exception as e:
            return False, f"Environment configs test failed: {str(e)}"
    
    def test_monitoring_configs(self) -> Tuple[bool, str]:
        """Test monitoring configuration files"""
        try:
            results = []
            
            # Check monitoring files
            monitoring_files = [
                'monitoring/prometheus.yml',
                'nginx/nginx.conf',
                'scripts/health_check.py',
                'scripts/production_smoke_test.py'
            ]
            
            found_files = []
            missing_files = []
            
            for file in monitoring_files:
                if os.path.exists(file):
                    found_files.append(file)
                else:
                    missing_files.append(file)
            
            if found_files:
                results.append(f"Found: {', '.join(found_files)}")
            
            if missing_files:
                results.append(f"Missing: {', '.join(missing_files)}")
            
            # Most monitoring files should exist
            if len(found_files) < len(monitoring_files) * 0.8:
                return False, f"Insufficient monitoring configs: {len(found_files)}/{len(monitoring_files)}"
            
            return True, f"Monitoring configs: {'; '.join(results)}"
            
        except Exception as e:
            return False, f"Monitoring configs test failed: {str(e)}"
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all CI/CD smoke tests"""
        tests = [
            ('github_actions_config', self.test_github_actions_config),
            ('pre_commit_config', self.test_pre_commit_config),
            ('deployment_script', self.test_deployment_script),
            ('docker_configs', self.test_docker_configs),
            ('environment_configs', self.test_environment_configs),
            ('monitoring_configs', self.test_monitoring_configs),
        ]
        
        for name, test_func in tests:
            try:
                success, message = test_func()
                self.results[name] = {
                    'status': 'passed' if success else 'failed',
                    'message': message,
                    'timestamp': time.time()
                }
            except Exception as e:
                self.results[name] = {
                    'status': 'error',
                    'message': f"Test failed with exception: {str(e)}",
                    'timestamp': time.time()
                }
        
        # Calculate overall results
        passed_tests = sum(1 for r in self.results.values() if r['status'] == 'passed')
        total_tests = len(self.results)
        
        self.results['overall'] = {
            'status': 'passed' if passed_tests == total_tests else 'failed',
            'passed_tests': passed_tests,
            'total_tests': total_tests,
            'pass_percentage': (passed_tests / total_tests) * 100,
            'timestamp': time.time(),
            'duration_ms': (time.time() - self.start_time) * 1000
        }
        
        return self.results
    
    def print_results(self):
        """Print CI/CD smoke test results"""
        print("=" * 70)
        print("NCFD Phase 9 CI/CD Pipeline Smoke Test Results")
        print("=" * 70)
        
        for name, result in self.results.items():
            if name == 'overall':
                continue
                
            status_icon = "✅" if result['status'] == 'passed' else "❌"
            print(f"{status_icon} {name.replace('_', ' ').upper()}: {result['status']}")
            print(f"   {result['message']}")
            print()
        
        # Overall results
        overall = self.results['overall']
        overall_icon = "✅" if overall['status'] == 'passed' else "❌"
        print(f"{overall_icon} OVERALL RESULTS: {overall['status'].upper()}")
        print(f"   Pass Rate: {overall['pass_percentage']:.1f}% ({overall['passed_tests']}/{overall['total_tests']})")
        print(f"   Duration: {overall['duration_ms']:.1f}ms")
        print("=" * 70)
        
        return overall['status'] == 'passed'

def main():
    """Main entry point"""
    import time
    
    print("🚀 Starting NCFD Phase 9 CI/CD Pipeline Smoke Tests...")
    print()
    
    # Run CI/CD smoke tests
    tester = CICDSmokeTest()
    results = tester.run_all_tests()
    
    # Print results
    all_passed = tester.print_results()
    
    # Exit with appropriate code
    if all_passed:
        print("🎉 All CI/CD smoke tests passed! Pipeline is ready for production.")
        sys.exit(0)
    else:
        print("⚠️  Some CI/CD smoke tests failed. Please review and fix issues before proceeding.")
        sys.exit(1)

if __name__ == "__main__":
    main()
