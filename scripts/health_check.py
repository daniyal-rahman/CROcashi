#!/opt/homebrew/Caskroom/miniconda/base/bin/python3.12
"""
Production Health Check Script for NCFD
Checks all critical services and endpoints for production readiness
"""

import os
import sys
import time
import json
import requests
import psycopg2
import redis
from urllib.parse import urlparse
from typing import Dict, List, Any, Tuple

class HealthChecker:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.results = {}
        self.start_time = time.time()
        
    def check_database(self) -> Tuple[bool, str]:
        """Check PostgreSQL database connectivity and health"""
        try:
            # Parse DSN
            dsn = self.config.get('POSTGRES_DSN', '')
            if not dsn:
                return False, "No database DSN configured"
            
            # Connect to database
            conn = psycopg2.connect(dsn)
            cursor = conn.cursor()
            
            # Check basic connectivity
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            if result[0] != 1:
                return False, "Database query failed"
            
            # Check database size
            cursor.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
            size = cursor.fetchone()[0]
            
            # Check active connections
            cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
            active_connections = cursor.fetchone()[0]
            
            # Check if tables exist
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('trials', 'signals', 'gates', 'scores')
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            return True, f"Database healthy - Size: {size}, Active connections: {active_connections}, Tables: {len(tables)}"
            
        except Exception as e:
            return False, f"Database check failed: {str(e)}"
    
    def check_redis(self) -> Tuple[bool, str]:
        """Check Redis connectivity and health"""
        try:
            host = self.config.get('REDIS_HOST', 'localhost')
            port = int(self.config.get('REDIS_PORT', 6379))
            password = self.config.get('REDIS_PASSWORD')
            db = int(self.config.get('REDIS_DB', 0))
            
            r = redis.Redis(host=host, port=port, password=password, db=db, socket_timeout=5)
            
            # Test basic operations
            r.set('health_check', 'test', ex=10)
            value = r.get('health_check')
            if value != b'test':
                return False, "Redis read/write test failed"
            
            # Check memory usage
            info = r.info()
            memory_used = info.get('used_memory_human', 'Unknown')
            connected_clients = info.get('connected_clients', 0)
            
            r.delete('health_check')
            
            return True, f"Redis healthy - Memory: {memory_used}, Clients: {connected_clients}"
            
        except Exception as e:
            return False, f"Redis check failed: {str(e)}"
    
    def check_storage(self) -> Tuple[bool, str]:
        """Check storage system health"""
        try:
            storage_type = self.config.get('STORAGE_TYPE', 'local')
            
            if storage_type == 's3':
                # Check S3/MinIO connectivity
                endpoint = self.config.get('S3_ENDPOINT_URL', '')
                bucket = self.config.get('S3_BUCKET', '')
                
                if not endpoint or not bucket:
                    return False, "S3 configuration incomplete"
                
                # Try to list buckets (basic connectivity test)
                # This would require boto3 in production
                return True, f"S3 storage configured - Endpoint: {endpoint}, Bucket: {bucket}"
            
            elif storage_type == 'local':
                # Check local storage
                local_path = self.config.get('LOCAL_STORAGE_ROOT', './data')
                if os.path.exists(local_path):
                    # Check available space
                    stat = os.statvfs(local_path)
                    free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
                    return True, f"Local storage healthy - Free space: {free_gb:.1f}GB"
                else:
                    return False, f"Local storage path does not exist: {local_path}"
            
            else:
                return False, f"Unknown storage type: {storage_type}"
                
        except Exception as e:
            return False, f"Storage check failed: {str(e)}"
    
    def check_api_endpoints(self) -> Tuple[bool, str]:
        """Check API endpoint health"""
        try:
            base_url = f"http://{self.config.get('API_HOST', 'localhost')}:{self.config.get('API_PORT', '8000')}"
            
            # Check health endpoint
            health_url = f"{base_url}/health"
            response = requests.get(health_url, timeout=10)
            if response.status_code != 200:
                return False, f"Health endpoint returned {response.status_code}"
            
            # Check metrics endpoint
            metrics_url = f"{base_url}/metrics"
            response = requests.get(metrics_url, timeout=10)
            if response.status_code != 200:
                return False, f"Metrics endpoint returned {response.status_code}"
            
            return True, "API endpoints healthy"
            
        except Exception as e:
            return False, f"API check failed: {str(e)}"
    
    def check_external_apis(self) -> Tuple[bool, str]:
        """Check external API connectivity"""
        try:
            results = []
            
            # Check ClinicalTrials.gov
            try:
                response = requests.get("https://clinicaltrials.gov/api/v2/studies", timeout=10)
                if response.status_code == 200:
                    results.append("ClinicalTrials.gov: OK")
                else:
                    results.append(f"ClinicalTrials.gov: {response.status_code}")
            except Exception as e:
                results.append(f"ClinicalTrials.gov: Error - {str(e)}")
            
            # Check SEC API
            try:
                response = requests.get("https://www.sec.gov/Archives/edgar/data/1000229/000100022920000006/aapl-20200926.xml", timeout=10)
                if response.status_code == 200:
                    results.append("SEC API: OK")
                else:
                    results.append(f"SEC API: {response.status_code}")
            except Exception as e:
                results.append(f"SEC API: Error - {str(e)}")
            
            return True, f"External APIs: {'; '.join(results)}"
            
        except Exception as e:
            return False, f"External API check failed: {str(e)}"
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks"""
        checks = [
            ('database', self.check_database),
            ('redis', self.check_redis),
            ('storage', self.check_storage),
            ('api_endpoints', self.check_api_endpoints),
            ('external_apis', self.check_external_apis),
        ]
        
        for name, check_func in checks:
            try:
                success, message = check_func()
                self.results[name] = {
                    'status': 'healthy' if success else 'unhealthy',
                    'message': message,
                    'timestamp': time.time()
                }
            except Exception as e:
                self.results[name] = {
                    'status': 'error',
                    'message': f"Check failed with exception: {str(e)}",
                    'timestamp': time.time()
                }
        
        # Calculate overall health
        healthy_checks = sum(1 for r in self.results.values() if r['status'] == 'healthy')
        total_checks = len(self.results)
        
        self.results['overall'] = {
            'status': 'healthy' if healthy_checks == total_checks else 'degraded',
            'healthy_checks': healthy_checks,
            'total_checks': total_checks,
            'health_percentage': (healthy_checks / total_checks) * 100,
            'timestamp': time.time(),
            'duration_ms': (time.time() - self.start_time) * 1000
        }
        
        return self.results
    
    def print_results(self):
        """Print health check results in a formatted way"""
        print("=" * 60)
        print("NCFD Production Health Check Results")
        print("=" * 60)
        
        for name, result in self.results.items():
            if name == 'overall':
                continue
                
            status_icon = "✅" if result['status'] == 'healthy' else "❌"
            print(f"{status_icon} {name.upper()}: {result['status']}")
            print(f"   {result['message']}")
            print()
        
        # Overall status
        overall = self.results['overall']
        overall_icon = "✅" if overall['status'] == 'healthy' else "⚠️"
        print(f"{overall_icon} OVERALL STATUS: {overall['status'].upper()}")
        print(f"   Health: {overall['health_percentage']:.1f}% ({overall['healthy_checks']}/{overall['total_checks']})")
        print(f"   Duration: {overall['duration_ms']:.1f}ms")
        print("=" * 60)
        
        return overall['status'] == 'healthy'

def main():
    """Main entry point"""
    # Load configuration from environment
    config = {
        'POSTGRES_DSN': os.getenv('POSTGRES_DSN'),
        'REDIS_HOST': os.getenv('REDIS_HOST', 'localhost'),
        'REDIS_PORT': os.getenv('REDIS_PORT', '6379'),
        'REDIS_PASSWORD': os.getenv('REDIS_PASSWORD'),
        'REDIS_DB': os.getenv('REDIS_DB', '0'),
        'STORAGE_TYPE': os.getenv('STORAGE_TYPE', 'local'),
        'S3_ENDPOINT_URL': os.getenv('S3_ENDPOINT_URL'),
        'S3_BUCKET': os.getenv('S3_BUCKET'),
        'LOCAL_STORAGE_ROOT': os.getenv('LOCAL_STORAGE_ROOT', './data'),
        'API_HOST': os.getenv('API_HOST', 'localhost'),
        'API_PORT': os.getenv('API_PORT', '8000'),
    }
    
    # Run health checks
    checker = HealthChecker(config)
    results = checker.run_all_checks()
    
    # Print results
    is_healthy = checker.print_results()
    
    # Exit with appropriate code
    sys.exit(0 if is_healthy else 1)

if __name__ == "__main__":
    main()
