"""
OpenAI LLM Client for Literature Evaluation

This module provides a concrete implementation of the LLM client interface
for making OpenAI API calls to GPT-5-mini for clinical trial evaluation.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class OpenAIClient:
    """OpenAI API client for LLM evaluation."""
    
    def __init__(self, model: str = "gpt-5-mini", api_key: Optional[str] = None):
        """
        Initialize OpenAI client.
        
        Args:
            model: OpenAI model to use (default: gpt-5-mini)
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.model = model
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        # Configure OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        
        logger.info(f"OpenAI client initialized with model: {model}")
    
    def evaluate(self, prompt: str, **kwargs):
        """
        Evaluate a prompt using the LLM.
        
        Args:
            prompt: The prompt to evaluate
            **kwargs: Additional arguments for the LLM
            
        Returns:
            LLM response
        """
        logger.info(f"🔍 LLM CLIENT CALLED with prompt: {prompt[:100]}...")
        logger.info(f"🔍 LLM CLIENT kwargs: {kwargs}")
        
        try:
            # GPT-5-mini requires max_completion_tokens instead of max_tokens
            if 'max_tokens' in kwargs and self.model == "gpt-5-mini":
                kwargs['max_completion_tokens'] = kwargs.pop('max_tokens')
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                **kwargs
            )
            result = response.choices[0].message.content
            logger.info(f"🔍 LLM CLIENT RESPONSE: {result[:100]}...")
            return result
        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}")
            raise
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the current model."""
        return {
            'model': self.model,
            'provider': 'OpenAI',
            'api_key_configured': bool(self.api_key),
            'timestamp': datetime.now().isoformat()
        }


class LLMClientInterface:
    """Interface for LLM clients to ensure compatibility."""
    
    def __init__(self, client_type: str = "openai", **kwargs):
        """
        Initialize LLM client interface.
        
        Args:
            client_type: Type of client ("openai" or "gemini")
            **kwargs: Client-specific configuration
        """
        if client_type == "openai":
            self.client = OpenAIClient(**kwargs)
        elif client_type == "gemini":
            # TODO: Implement Gemini client
            raise NotImplementedError("Gemini client not yet implemented")
        else:
            raise ValueError(f"Unknown client type: {client_type}")
    
    def evaluate(self, prompt: str, **kwargs) -> str:
        """Delegate evaluation to underlying client."""
        return self.client.evaluate(prompt, **kwargs)
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information from underlying client."""
        return self.client.get_model_info()


# Convenience function for creating LLM clients
def create_llm_client(client_type: str = "openai", **kwargs) -> LLMClientInterface:
    """
    Create an LLM client instance.
    
    Args:
        client_type: Type of client to create
        **kwargs: Client-specific configuration
        
    Returns:
        Configured LLM client instance
    """
    return LLMClientInterface(client_type, **kwargs)
