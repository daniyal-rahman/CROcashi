"""
Environment loader utility for tests.

This module provides utilities to automatically load environment variables
for tests, ensuring consistent test environment setup.
"""

import os
from pathlib import Path
from typing import Dict, Optional


def load_env_file(env_file: Path) -> bool:
    """Load environment variables from a file."""
    try:
        from dotenv import load_dotenv
        if env_file.exists():
            load_dotenv(env_file, override=True)
            return True
    except ImportError:
        # Fallback to manual parsing if python-dotenv is not available
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            return True
    return False


def setup_test_environment(project_root: Optional[Path] = None) -> Dict[str, str]:
    """
    Setup test environment variables.
    
    Args:
        project_root: Root directory of the project. If None, will be inferred.
        
    Returns:
        Dictionary of environment variables that were set.
    """
    if project_root is None:
        # Assume we're in tests/utils/, so go up two levels
        project_root = Path(__file__).parent.parent.parent
    
    loaded_vars = {}
    
    # Try to load .env file from project root
    env_file = project_root / '.env'
    if load_env_file(env_file):
        print(f"✅ Loaded environment variables from: {env_file}")
        loaded_vars['source'] = str(env_file)
    
    # Set default test values if not already set
    # Only override if we're in test mode or if the variable is not set
    test_defaults = {
        'OPENAI_API_KEY': 'test-key-for-testing',
        'STORAGE_TYPE': 'local',
        'LOCAL_STORAGE_ROOT': './data/test',
        'TEST_MODE': 'true',
        'LOG_LEVEL': 'WARNING'
    }
    
    # For database, use the same database as production (ncfd)
    # All tests now use the same database to avoid confusion
    test_defaults.update({
        'DB_HOST': 'localhost',
        'DB_PORT': '5433',
        'DB_USER': 'ncfd',
        'DB_PASS': 'ncfd',
        'DB_NAME': 'ncfd',  # Use same database as production
        'PSQL_DSN': 'postgresql+psycopg2://ncfd:ncfd@localhost:5433/ncfd',
        'DATABASE_URL': 'postgresql://ncfd:ncfd@localhost:5433/ncfd',
        'POSTGRES_DSN': 'postgresql+psycopg2://ncfd:ncfd@localhost:5433/ncfd',
        'PGPASSWORD': 'ncfd'  # Disable password prompts
    })
    
    # Only use SQLite if explicitly requested
    if 'TEST_DATABASE' in os.environ and os.environ['TEST_DATABASE'] == 'sqlite':
        test_defaults.update({
            'PSQL_DSN': 'sqlite:///test.db',
            'DATABASE_URL': 'sqlite:///test.db',
            'POSTGRES_DSN': 'sqlite:///test.db'
        })
    
    for key, default_value in test_defaults.items():
        # Always override with test values for database-related variables
        # to ensure we're using the testing database, not production
        if key in ['PSQL_DSN', 'DATABASE_URL', 'POSTGRES_DSN', 'DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASS', 'DB_NAME']:
            os.environ[key] = default_value
            loaded_vars[key] = default_value
            print(f"🔧 Override {key}={default_value} (testing database)")
        elif key not in os.environ:
            os.environ[key] = default_value
            loaded_vars[key] = default_value
            print(f"🔧 Set default {key}={default_value}")
        else:
            loaded_vars[key] = os.environ[key]
    
    return loaded_vars


def get_test_env() -> Dict[str, str]:
    """Get current test environment variables."""
    return {
        'PSQL_DSN': os.environ.get('PSQL_DSN', 'postgresql+psycopg2://ncfd:ncfd@localhost:5433/ncfd'),
        'DATABASE_URL': os.environ.get('DATABASE_URL', 'postgresql://ncfd:ncfd@localhost:5433/ncfd'),
        'POSTGRES_DSN': os.environ.get('POSTGRES_DSN', 'postgresql+psycopg2://ncfd:ncfd@localhost:5433/ncfd'),
        'DB_HOST': os.environ.get('DB_HOST', 'localhost'),
        'DB_PORT': os.environ.get('DB_PORT', '5433'),
        'DB_USER': os.environ.get('DB_USER', 'ncfd'),
        'DB_PASS': os.environ.get('DB_PASS', 'ncfd'),
        'DB_NAME': os.environ.get('DB_NAME', 'ncfd'),
        'PGPASSWORD': os.environ.get('PGPASSWORD', 'ncfd'),
        'OPENAI_API_KEY': os.environ.get('OPENAI_API_KEY', 'test-key-for-testing'),
        'STORAGE_TYPE': os.environ.get('STORAGE_TYPE', 'local'),
        'LOCAL_STORAGE_ROOT': os.environ.get('LOCAL_STORAGE_ROOT', './data/test'),
        'TEST_MODE': os.environ.get('TEST_MODE', 'true'),
        'LOG_LEVEL': os.environ.get('LOG_LEVEL', 'WARNING')
    }


def ensure_test_env():
    """Ensure test environment is properly set up."""
    return setup_test_environment()
