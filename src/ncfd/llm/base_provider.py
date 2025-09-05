"""
Base LLM Provider Interface

Abstract base class that all LLM providers must implement.
Defines the standard interface for LLM interactions.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncIterator
import time
import logging
from datetime import datetime

from .models import LLMRequest, LLMResponse, LLMError, LLMProviderError


logger = logging.getLogger(__name__)


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""
    
    def __init__(self, provider_name: str, config: Dict[str, Any]):
        """
        Initialize the provider.
        
        Args:
            provider_name: Name of the provider (e.g., "openai", "anthropic", "gemini")
            config: Provider-specific configuration
        """
        self.provider_name = provider_name
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{provider_name}")
        
        # Performance tracking
        self.total_requests = 0
        self.total_errors = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        
        # Rate limiting (optional - providers can override)
        self.rate_limit_requests_per_minute = config.get("rate_limit_requests_per_minute", 60)
        self.request_timestamps = []
        
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Complete an LLM request.
        
        Args:
            request: Standardized LLM request
            
        Returns:
            Standardized LLM response
            
        Raises:
            LLMProviderError: If the provider API call fails
            LLMValidationError: If the request is invalid
        """
        pass
    
    @abstractmethod
    async def stream_complete(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream completion tokens.
        
        Args:
            request: Standardized LLM request with stream=True
            
        Yields:
            Individual tokens or text chunks
            
        Raises:
            LLMProviderError: If the provider API call fails
        """
        pass
    
    @abstractmethod
    def validate_request(self, request: LLMRequest) -> bool:
        """
        Validate a request for this provider.
        
        Args:
            request: LLM request to validate
            
        Returns:
            True if valid
            
        Raises:
            LLMValidationError: If request is invalid
        """
        pass
    
    @abstractmethod
    def get_model_capabilities(self, model: str) -> Dict[str, bool]:
        """
        Get capabilities for a specific model.
        
        Args:
            model: Model name
            
        Returns:
            Dictionary of capabilities (json_output, function_calling, etc.)
        """
        pass
    
    def _check_rate_limit(self) -> None:
        """Check if we're within rate limits."""
        now = time.time()
        
        # Remove requests older than 1 minute
        self.request_timestamps = [ts for ts in self.request_timestamps if now - ts < 60]
        
        if len(self.request_timestamps) >= self.rate_limit_requests_per_minute:
            sleep_time = 60 - (now - self.request_timestamps[0])
            if sleep_time > 0:
                self.logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
        
        self.request_timestamps.append(now)
    
    def _track_request(self, request: LLMRequest, response: Optional[LLMResponse] = None, error: Optional[Exception] = None) -> None:
        """Track request metrics."""
        self.total_requests += 1
        
        if error:
            self.total_errors += 1
            self.logger.error(f"Request failed: {error}")
        
        if response:
            self.total_tokens += response.usage.total_tokens
            self.logger.debug(f"Request completed: {response.usage.total_tokens} tokens")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics."""
        error_rate = self.total_errors / self.total_requests if self.total_requests > 0 else 0
        
        return {
            "provider": self.provider_name,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": error_rate,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost
        }
    
    def reset_stats(self) -> None:
        """Reset provider statistics."""
        self.total_requests = 0
        self.total_errors = 0
        self.total_tokens = 0
        self.total_cost = 0.0
