"""
LLM Configuration Management

Handles loading and validating LLM configurations from YAML files.
Supports provider-specific settings and worker overrides.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging

from .models import LLMConfigurationError

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, continue without it

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    capabilities: List[str] = field(default_factory=list)
    max_tokens: int = 4000
    temperature: float = 0.1
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0
    supports_system_message: bool = True
    supports_function_calling: bool = False
    supports_json_output: bool = False
    supports_streaming: bool = True


@dataclass 
class ProviderConfig:
    """Configuration for an LLM provider."""
    api_key_env: str
    base_url_env: Optional[str] = None
    default_model: str = ""
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    rate_limit_requests_per_minute: int = 60
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


@dataclass
class LLMConfig:
    """Main LLM configuration."""
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    default_provider: str = "openai"
    workers: Dict[str, Dict[str, str]] = field(default_factory=dict)  # worker_name -> {provider, model}
    enable_fallback: bool = True
    fallback_order: List[str] = field(default_factory=lambda: ["openai", "anthropic", "gemini"])
    
    def get_provider_config(self, provider_name: str) -> ProviderConfig:
        """Get configuration for a specific provider."""
        if provider_name not in self.providers:
            raise LLMConfigurationError(f"Provider '{provider_name}' not configured")
        return self.providers[provider_name]
    
    def get_worker_config(self, worker_name: str) -> Dict[str, str]:
        """Get LLM configuration for a specific worker."""
        if worker_name in self.workers:
            return self.workers[worker_name]
        
        # Return default configuration
        return {
            "provider": self.default_provider,
            "model": self.providers[self.default_provider].default_model
        }
    
    def get_model_config(self, provider: str, model: str) -> ModelConfig:
        """Get configuration for a specific model."""
        provider_config = self.get_provider_config(provider)
        if model not in provider_config.models:
            # Return default model config
            return ModelConfig()
        return provider_config.models[model]


def load_llm_config(config_path: Optional[str] = None) -> LLMConfig:
    """
    Load LLM configuration from YAML file.
    
    Args:
        config_path: Path to config file. If None, searches default locations.
        
    Returns:
        LLM configuration object
        
    Raises:
        LLMConfigurationError: If config file not found or invalid
    """
    if config_path is None:
        # Try multiple default locations
        project_root = Path(__file__).parent.parent.parent.parent
        candidates = [
            project_root / "config" / "llm_models.yaml",
            project_root / "config" / "config.yaml",
            project_root / "config" / "pipeline_config.yaml",
        ]
        
        config_path = None
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break
        
        if config_path is None:
            logger.warning("No LLM config file found, using default configuration")
            return _get_default_config()
    
    try:
        with open(config_path, 'r') as f:
            raw_config = yaml.safe_load(f)
        
        # Extract LLM-specific configuration
        llm_config_data = raw_config.get('llm', raw_config)
        
        return _parse_config(llm_config_data)
        
    except Exception as e:
        raise LLMConfigurationError(f"Failed to load LLM config from {config_path}: {e}")


def _parse_config(config_data: Dict[str, Any]) -> LLMConfig:
    """Parse raw configuration data into LLMConfig object."""
    providers = {}
    
    # Parse provider configurations
    for provider_name, provider_data in config_data.get('providers', {}).items():
        models = {}
        
        # Parse model configurations
        for model_name, model_data in provider_data.get('models', {}).items():
            models[model_name] = ModelConfig(
                capabilities=model_data.get('capabilities', []),
                max_tokens=model_data.get('max_tokens', 4000),
                temperature=model_data.get('temperature', 0.1),
                cost_per_input_token=model_data.get('cost_per_input_token', 0.0),
                cost_per_output_token=model_data.get('cost_per_output_token', 0.0),
                supports_system_message=model_data.get('supports_system_message', True),
                supports_function_calling='function_calling' in model_data.get('capabilities', []),
                supports_json_output='json_output' in model_data.get('capabilities', []),
                supports_streaming=model_data.get('supports_streaming', True)
            )
        
        providers[provider_name] = ProviderConfig(
            api_key_env=provider_data.get('api_key_env', f"{provider_name.upper()}_API_KEY"),
            base_url_env=provider_data.get('base_url_env'),
            default_model=provider_data.get('default_model', ''),
            models=models,
            rate_limit_requests_per_minute=provider_data.get('rate_limit_requests_per_minute', 60),
            timeout_seconds=provider_data.get('timeout_seconds', 30),
            max_retries=provider_data.get('max_retries', 3),
            retry_delay_seconds=provider_data.get('retry_delay_seconds', 1.0)
        )
    
    return LLMConfig(
        providers=providers,
        default_provider=config_data.get('default_provider', 'openai'),
        workers=config_data.get('workers', {}),
        enable_fallback=config_data.get('enable_fallback', True),
        fallback_order=config_data.get('fallback_order', ['openai', 'anthropic', 'gemini'])
    )


def _get_default_config() -> LLMConfig:
    """Get default LLM configuration when no config file is found."""
    
    # Default OpenAI model config
    openai_models = {
        "gpt-4o": ModelConfig(
            capabilities=["json_output", "function_calling"],
            max_tokens=4000,
            temperature=0.1,
            supports_function_calling=True,
            supports_json_output=True
        ),
        "gpt-5-mini": ModelConfig(
            capabilities=["json_output", "web_search"],
            max_tokens=2000,
            temperature=0.1,
            supports_json_output=True
        )
    }
    
    # Default provider configs
    providers = {
        "openai": ProviderConfig(
            api_key_env="OPENAI_API_KEY",
            base_url_env="OPENAI_BASE_URL",
            default_model="gpt-4o",
            models=openai_models
        )
    }
    
    return LLMConfig(
        providers=providers,
        default_provider="openai",
        fallback_order=["openai"]
    )


def validate_environment(config: LLMConfig) -> List[str]:
    """
    Validate that required environment variables are set.
    
    Args:
        config: LLM configuration to validate
        
    Returns:
        List of missing environment variables
    """
    missing_vars = []
    
    for provider_name, provider_config in config.providers.items():
        if not os.getenv(provider_config.api_key_env):
            missing_vars.append(provider_config.api_key_env)
    
    return missing_vars
