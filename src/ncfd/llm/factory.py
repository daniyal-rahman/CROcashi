"""
LLM Provider Factory

Creates and manages LLM provider instances based on configuration.
Supports provider selection, fallback, and worker-specific overrides.
"""

import logging
from typing import Dict, Any, Optional, List
from .base_provider import BaseLLMProvider
from .config import LLMConfig, load_llm_config
from .models import LLMConfigurationError
from .providers.openai_provider import OpenAIProvider
from ..utils.config_manager import get_config_manager
from ..utils.error_handler import get_error_handler, safe_execute

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """Factory for creating LLM provider instances."""
    
    # Registry of available providers
    _providers = {
        "openai": OpenAIProvider,
        # Future providers will be added here:
        # "anthropic": AnthropicProvider,
        # "gemini": GeminiProvider,
    }
    
    def __init__(self, config: Optional[LLMConfig] = None):
        """
        Initialize the factory.
        
        Args:
            config: LLM configuration. If None, loads from default locations.
        """
        self.config = config or load_llm_config()
        self._provider_instances: Dict[str, BaseLLMProvider] = {}
        self.logger = logging.getLogger(__name__)
    
    def create_provider(self, provider_name: str, model_name: Optional[str] = None) -> BaseLLMProvider:
        """
        Create a provider instance.
        
        Args:
            provider_name: Name of the provider to create
            model_name: Optional model name to use (defaults to provider's default)
            
        Returns:
            Provider instance
            
        Raises:
            LLMConfigurationError: If provider not found or not configured
        """
        if provider_name not in self._providers:
            available = list(self._providers.keys())
            raise LLMConfigurationError(
                f"Provider '{provider_name}' not available. Available providers: {available}"
            )
        
        # Get provider configuration
        try:
            provider_config = self.config.get_provider_config(provider_name)
        except LLMConfigurationError as e:
            raise LLMConfigurationError(f"Provider '{provider_name}' not configured: {e}")
        
        # Use provided model name or default
        if model_name is None:
            model_name = provider_config.default_model
        
        # Check if already instantiated with this model
        cache_key = f"{provider_name}_{model_name}"
        if cache_key in self._provider_instances:
            return self._provider_instances[cache_key]
        
        # Create provider instance with model name
        provider_dict = provider_config.__dict__.copy()
        provider_dict["model"] = model_name
        
        provider_class = self._providers[provider_name]
        provider_instance = provider_class(provider_dict)
        
        # Cache the instance
        self._provider_instances[cache_key] = provider_instance
        
        self.logger.info(f"Created {provider_name} provider instance with model {model_name}")
        return provider_instance
    
    def create_for_worker(self, worker_name: str) -> BaseLLMProvider:
        """
        Create a provider instance for a specific worker.
        
        Args:
            worker_name: Name of the worker
            
        Returns:
            Provider instance configured for the worker
        """
        worker_config = self.config.get_worker_config(worker_name)
        provider_name = worker_config.get("provider", self.config.default_provider)
        model_name = worker_config.get("model", self.config.providers[provider_name].default_model)
        
        self.logger.debug(f"Creating provider '{provider_name}' for worker '{worker_name}' with model '{model_name}'")
        
        # Get provider configuration and add the model name
        provider_config = self.config.get_provider_config(provider_name)
        provider_dict = provider_config.__dict__.copy()
        provider_dict["model"] = model_name
        
        # Create provider instance with model name
        provider_class = self._providers[provider_name]
        provider_instance = provider_class(provider_dict)
        
        # Cache the instance
        self._provider_instances[f"{provider_name}_{model_name}"] = provider_instance
        
        self.logger.info(f"Created {provider_name} provider instance with model {model_name}")
        return provider_instance
    
    def get_model_for_worker(self, worker_name: str) -> str:
        """
        Get the model name configured for a specific worker.
        
        Args:
            worker_name: Name of the worker
            
        Returns:
            Model name
        """
        worker_config = self.config.get_worker_config(worker_name)
        return worker_config.get("model", self.config.providers[self.config.default_provider].default_model)
    
    def create_with_fallback(self, preferred_provider: Optional[str] = None) -> BaseLLMProvider:
        """
        Create a provider with fallback support.
        
        Args:
            preferred_provider: Preferred provider name. If None, uses default.
            
        Returns:
            Provider instance
            
        Raises:
            LLMConfigurationError: If no providers are available
        """
        providers_to_try = []
        
        if preferred_provider:
            providers_to_try.append(preferred_provider)
        
        if self.config.enable_fallback:
            providers_to_try.extend(self.config.fallback_order)
        else:
            providers_to_try.append(self.config.default_provider)
        
        # Remove duplicates while preserving order
        providers_to_try = list(dict.fromkeys(providers_to_try))
        
        last_error = None
        for provider_name in providers_to_try:
            try:
                return self.create_provider(provider_name)
            except Exception as e:
                last_error = e
                self.logger.warning(f"Failed to create provider '{provider_name}': {e}")
                continue
        
        raise LLMConfigurationError(f"No providers available. Last error: {last_error}")
    
    def list_available_providers(self) -> List[str]:
        """Get list of available provider names."""
        return list(self._providers.keys())
    
    def list_configured_providers(self) -> List[str]:
        """Get list of configured provider names."""
        return list(self.config.providers.keys())
    
    def get_provider_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all instantiated providers."""
        stats = {}
        for provider_name, provider in self._provider_instances.items():
            stats[provider_name] = provider.get_stats()
        return stats
    
    def reset_all_stats(self) -> None:
        """Reset statistics for all providers."""
        for provider in self._provider_instances.values():
            provider.reset_stats()
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type) -> None:
        """
        Register a new provider class.
        
        Args:
            name: Provider name
            provider_class: Provider class that inherits from BaseLLMProvider
        """
        if not issubclass(provider_class, BaseLLMProvider):
            raise ValueError(f"Provider class must inherit from BaseLLMProvider")
        
        cls._providers[name] = provider_class
        logger.info(f"Registered provider: {name}")


# Global factory instance for convenience
_default_factory: Optional[LLMProviderFactory] = None


def get_default_factory() -> LLMProviderFactory:
    """Get the default global factory instance."""
    global _default_factory
    if _default_factory is None:
        _default_factory = LLMProviderFactory()
    return _default_factory


def create_provider(provider_name: str) -> BaseLLMProvider:
    """Convenience function to create a provider using the default factory."""
    return get_default_factory().create_provider(provider_name)


def create_for_worker(worker_name: str) -> BaseLLMProvider:
    """Convenience function to create a provider for a worker using the default factory."""
    return get_default_factory().create_for_worker(worker_name)
