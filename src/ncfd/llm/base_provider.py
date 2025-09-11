"""
Base LLM Provider Interface

Abstract base class that all LLM providers must implement.
Defines the standard interface for LLM interactions.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncIterator
import time
import asyncio
import logging
from datetime import datetime

from .models import LLMRequest, LLMResponse, LLMError, LLMProviderError
from .concurrency_manager import concurrency_manager


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
        
        # Retry configuration
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay_seconds = config.get("retry_delay_seconds", 1.0)
        self.backoff_multiplier = config.get("backoff_multiplier", 2.0)
        
        # Concurrency control - use global manager
        self.max_concurrent_requests = config.get("max_concurrent_requests", 10)
        # Configure global concurrency manager
        concurrency_manager.configure(self.max_concurrent_requests)
        self._concurrency_semaphore = concurrency_manager.get_semaphore()
        
        # Model name (can be overridden by providers)
        self.model_name = config.get("model", "unknown")
        
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
    
    async def _check_rate_limit(self) -> None:
        """Check if we're within rate limits with async sleep."""
        now = time.time()
        
        # Remove requests older than 1 minute
        self.request_timestamps = [ts for ts in self.request_timestamps if now - ts < 60]
        
        if len(self.request_timestamps) >= self.rate_limit_requests_per_minute:
            sleep_time = 60 - (now - self.request_timestamps[0])
            if sleep_time > 0:
                self.logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                await asyncio.sleep(sleep_time)
        
        self.request_timestamps.append(now)
    
    async def _retry_with_backoff(self, func, *args, **kwargs):
        """Retry a function with exponential backoff for rate limit errors."""
        last_exception = None
        start_time = time.time()
        
        self.logger.info(f"🔄 Starting {func.__name__} with {self.max_retries} max retries")
        
        for attempt in range(self.max_retries + 1):
            attempt_start = time.time()
            self.logger.debug(f"🔄 Attempt {attempt + 1}/{self.max_retries + 1} for {func.__name__}")
            
            try:
                # Add timeout to prevent hanging
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=30.0)
                attempt_duration = time.time() - attempt_start
                total_duration = time.time() - start_time
                self.logger.info(f"✅ {func.__name__} succeeded on attempt {attempt + 1} (attempt: {attempt_duration:.2f}s, total: {total_duration:.2f}s)")
                return result
            except asyncio.TimeoutError:
                attempt_duration = time.time() - attempt_start
                total_duration = time.time() - start_time
                self.logger.error(f"⏰ Timeout in {func.__name__} (attempt {attempt + 1}/{self.max_retries + 1}) - attempt: {attempt_duration:.2f}s, total: {total_duration:.2f}s")
                if attempt == self.max_retries:
                    self.logger.error(f"💥 {func.__name__} failed after {self.max_retries + 1} attempts due to timeout")
                    raise
                continue
            except Exception as e:
                last_exception = e
                attempt_duration = time.time() - attempt_start
                total_duration = time.time() - start_time
                
                self.logger.warning(f"❌ Error in {func.__name__} (attempt {attempt + 1}/{self.max_retries + 1}): {e}")
                self.logger.debug(f"   Attempt duration: {attempt_duration:.2f}s, Total duration: {total_duration:.2f}s")
                
                # Check if this is a retryable error
                if not self._is_retryable_error(e):
                    # Check for specific quota errors and provide helpful message
                    error_str = str(e).lower()
                    if any(term in error_str for term in ['insufficient_quota', 'quota', 'billing', 'funds', 'exceeded your current quota']):
                        self.logger.error(f"💥 QUOTA ERROR - OpenAI API account needs funds!")
                        self.logger.error(f"💥 Error: {e}")
                        self.logger.error(f"💥 ACTION REQUIRED: Add funds to your OpenAI API account at https://platform.openai.com/account/billing")
                        raise LLMProviderError(
                            f"OpenAI API quota exceeded - please add funds to your account at https://platform.openai.com/account/billing. Original error: {e}",
                            provider="openai",
                            original_error=e
                        )
                    else:
                        self.logger.error(f"💥 Non-retryable error in {func.__name__}: {e}")
                        raise e
                
                # If this is the last attempt, raise the exception
                if attempt == self.max_retries:
                    self.logger.error(f"💥 Max retries ({self.max_retries}) exceeded for {func.__name__} after {total_duration:.2f}s")
                    raise e
                
                # Calculate backoff delay with cap
                delay = min(self.retry_delay_seconds * (self.backoff_multiplier ** attempt), 10.0)
                self.logger.warning(f"🔄 Retryable error in {func.__name__} (attempt {attempt + 1}/{self.max_retries + 1}): {e}. Retrying in {delay:.2f}s")
                
                await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        self.logger.error(f"💥 Unexpected end of retry loop for {func.__name__}")
        raise last_exception
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable (rate limit, temporary server error, etc.)."""
        error_str = str(error).lower()
        
        # Check for quota/insufficient funds errors - these should NOT be retried
        if any(term in error_str for term in ['insufficient_quota', 'quota', 'billing', 'funds', 'exceeded your current quota']):
            return False
        
        # Rate limit errors (429 but not quota-related)
        if any(term in error_str for term in ['rate limit', 'too many requests', '503', 'service unavailable']):
            return True
        
        # 429 errors that are NOT quota-related
        if '429' in error_str and not any(term in error_str for term in ['quota', 'insufficient', 'billing']):
            return True
        
        # Temporary server errors
        if any(term in error_str for term in ['500', '502', '504', 'timeout', 'connection']):
            return True
        
        # OpenAI specific errors
        if any(term in error_str for term in ['rate_limit_exceeded', 'server_error', 'temporary']):
            return True
        
        return False
    
    def get_concurrency_semaphore(self) -> asyncio.Semaphore:
        """Get the concurrency control semaphore."""
        return self._concurrency_semaphore
    
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
