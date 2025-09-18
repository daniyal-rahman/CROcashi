"""
Runtime Document Text Generation Module

Provides intelligent document text generation at runtime with caching and API integration.
"""

from .text_generator import RuntimeTextGenerator
from .text_cache import DocumentTextCache
from .api_clients import PubMedTextClient, PMCTextClient, UnpaywallTextClient
from .config import RUNTIME_TEXT_CONFIG

__all__ = [
    'RuntimeTextGenerator',
    'DocumentTextCache', 
    'PubMedTextClient',
    'PMCTextClient',
    'UnpaywallTextClient',
    'RUNTIME_TEXT_CONFIG'
]
