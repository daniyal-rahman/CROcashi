"""
LLM Abstraction Layer

This package provides a modular, provider-agnostic interface for LLM interactions.
Supports OpenAI, Anthropic, and Gemini with unified request/response handling.
"""

from .models import LLMRequest, LLMResponse, LLMError, LLMMessage, LLMGenerationConfig, LLMSchema
from .base_provider import BaseLLMProvider
from .base_worker import BaseLLMWorker, BaseLLMExtractor
from .factory import LLMProviderFactory
from .config import LLMConfig, load_llm_config
from .providers.openai_provider import OpenAIProvider

__all__ = [
    "LLMRequest",
    "LLMResponse", 
    "LLMError",
    "LLMMessage",
    "LLMGenerationConfig",
    "LLMSchema",
    "BaseLLMProvider",
    "BaseLLMWorker",
    "BaseLLMExtractor",
    "LLMProviderFactory",
    "LLMConfig",
    "load_llm_config",
    "OpenAIProvider"
]
