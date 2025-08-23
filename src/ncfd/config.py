"""
Configuration module for NCFD.

Provides centralized configuration loading and management.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


def get_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to config file. If None, uses default locations.
        
    Returns:
        Configuration dictionary
    """
    if config_path is None:
        # Try multiple default locations
        project_root = Path(__file__).parent.parent.parent
        candidates = [
            project_root / "config" / "config.yaml",
            project_root / "config" / "pipeline_config.yaml",
            project_root / "config" / "ctgov_config.yaml",
        ]
        
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break
        
        if config_path is None:
            # Return minimal default config
            return {
                'ctgov': {
                    'api': {
                        'base_url': 'https://clinicaltrials.gov/api/v2',
                        'timeout_seconds': 45,
                        'max_retries': 3,
                    },
                    'ingestion': {
                        'batch_size': 100,
                        'max_studies_per_run': 1000,
                        'default_since_days': 7,
                    }
                },
                'sec': {
                    'api': {
                        'base_url': 'https://data.sec.gov',
                        'timeout_seconds': 30,
                    }
                }
            }
    
    # Load YAML config
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config or {}


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv('DATABASE_URL', 'postgresql://ncfd:ncfd@localhost:5432/ncfd')


def get_postgres_dsn() -> str:
    """Get Postgres DSN from environment.""" 
    return os.getenv('POSTGRES_DSN', 'postgresql+psycopg2://ncfd:ncfd@localhost:5432/ncfd')
