"""
Centralized Configuration Manager

Provides consistent configuration loading and management across the entire application.
Eliminates duplication and inconsistencies in config handling.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union, Type, TypeVar
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class ConfigSection:
    """Represents a configuration section with validation."""
    name: str
    required: bool = False
    default: Any = None
    validator: Optional[callable] = None


class ConfigManager:
    """Centralized configuration manager with consistent loading patterns."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize config manager."""
        self.config_path = config_path
        self._config_cache: Optional[Dict[str, Any]] = None
        self.logger = logging.getLogger(__name__)
    
    def load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from YAML file with consistent error handling.
        
        Args:
            config_path: Path to config file. If None, searches default locations.
            
        Returns:
            Configuration dictionary
        """
        if config_path:
            self.config_path = config_path
        
        if self._config_cache is not None:
            return self._config_cache
        
        try:
            config_path = self._find_config_file()
            if not config_path:
                self.logger.warning("No config file found, using defaults")
                return self._get_default_config()
            
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            self._config_cache = config or {}
            self.logger.info(f"Loaded config from {config_path}")
            return self._config_cache
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return self._get_default_config()
    
    def get_section(self, section_name: str, default: Any = None) -> Dict[str, Any]:
        """Get a configuration section with consistent access pattern."""
        config = self.load_config()
        return config.get(section_name, default or {})
    
    def get_value(self, key_path: str, default: Any = None) -> Any:
        """
        Get a nested configuration value using dot notation.
        
        Args:
            key_path: Dot-separated path (e.g., 'ctgov.api.base_url')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        config = self.load_config()
        keys = key_path.split('.')
        
        current = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        
        return current
    
    def get_with_validation(self, key_path: str, validator: callable, default: Any = None) -> Any:
        """Get configuration value with validation."""
        value = self.get_value(key_path, default)
        if validator and not validator(value):
            self.logger.warning(f"Config validation failed for {key_path}: {value}")
            return default
        return value
    
    def create_config_object(self, config_class: Type[T], section_name: str) -> T:
        """
        Create a configuration object from a dataclass.
        
        Args:
            config_class: Dataclass configuration class
            section_name: Configuration section name
            
        Returns:
            Instance of config_class
        """
        section_config = self.get_section(section_name, {})
        
        try:
            # Try to use from_dict if available
            if hasattr(config_class, 'from_dict'):
                return config_class.from_dict(section_config)
            else:
                # Create instance with available fields
                return config_class(**{k: v for k, v in section_config.items() 
                                     if hasattr(config_class, k)})
        except Exception as e:
            self.logger.error(f"Failed to create config object {config_class.__name__}: {e}")
            # Return default instance
            return config_class()
    
    def _find_config_file(self) -> Optional[str]:
        """Find configuration file in standard locations."""
        if self.config_path and Path(self.config_path).exists():
            return self.config_path
        
        # Search standard locations
        project_root = Path(__file__).parent.parent.parent.parent
        candidates = [
            project_root / "config" / "core_system_config.yaml",
            project_root / "config" / "pipeline_config.yaml",
            project_root / "config" / "ctgov_config.yaml",
            project_root / "config" / "llm_models.yaml",
            project_root / "config.yaml",
            project_root / "config.yml",
        ]
        
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        
        return None
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
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
            },
            'pubmed': {
                'api': {
                    'base_url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils',
                    'timeout_seconds': 30,
                }
            },
            'llm': {
                'default_provider': 'openai',
                'default_model': 'gpt-4',
                'max_retries': 3,
            }
        }
    
    def reload_config(self):
        """Reload configuration from file."""
        self._config_cache = None
        return self.load_config()


# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    """Get global config manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager


def get_config(section_name: Optional[str] = None) -> Union[Dict[str, Any], Any]:
    """
    Convenience function for getting configuration.
    
    Args:
        section_name: Optional section name to get specific section
        
    Returns:
        Full config dict if section_name is None, otherwise section config
    """
    manager = get_config_manager()
    if section_name:
        return manager.get_section(section_name)
    return manager.load_config()


def get_config_value(key_path: str, default: Any = None) -> Any:
    """Convenience function for getting nested config values."""
    return get_config_manager().get_value(key_path, default)
