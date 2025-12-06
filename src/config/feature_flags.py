"""
Feature flags for experimental/optional features.

This module provides feature flags to enable/disable experimental features
such as LLM-based entity validation without requiring code changes.
"""
import os
from typing import Optional


class FeatureFlags:
    """Feature flags for experimental/optional features."""
    
    # LLM Entity Resolution
    USE_LLM_VALIDATION: bool = os.getenv('USE_LLM_VALIDATION', 'false').lower() == 'true'
    LLM_MODEL_PATH: Optional[str] = os.getenv('LLM_MODEL_PATH')
    LLM_CONFIDENCE_WEIGHT: float = float(os.getenv('LLM_CONFIDENCE_WEIGHT', '0.6'))
    
    # Thresholds for LLM invocation
    LLM_INVOKE_MIN_CONFIDENCE: float = float(os.getenv('LLM_INVOKE_MIN_CONFIDENCE', '0.60'))
    LLM_INVOKE_MAX_CONFIDENCE: float = float(os.getenv('LLM_INVOKE_MAX_CONFIDENCE', '0.90'))
    AUTO_MATCH_THRESHOLD: float = float(os.getenv('AUTO_MATCH_THRESHOLD', '0.85'))
    
    @classmethod
    def get_config_summary(cls) -> dict:
        """Get summary of current feature flag configuration."""
        return {
            'llm_validation_enabled': cls.USE_LLM_VALIDATION,
            'llm_model_path': cls.LLM_MODEL_PATH,
            'llm_confidence_weight': cls.LLM_CONFIDENCE_WEIGHT,
            'thresholds': {
                'llm_invoke_min': cls.LLM_INVOKE_MIN_CONFIDENCE,
                'llm_invoke_max': cls.LLM_INVOKE_MAX_CONFIDENCE,
                'auto_match': cls.AUTO_MATCH_THRESHOLD
            }
        }
    
    @classmethod
    def print_config(cls):
        """Print current configuration."""
        config = cls.get_config_summary()
        print("Feature Flags Configuration:")
        print(f"  LLM Validation: {'ENABLED' if config['llm_validation_enabled'] else 'DISABLED'}")
        print(f"  LLM Model Path: {config['llm_model_path'] or 'Not set'}")
        print(f"  LLM Confidence Weight: {config['llm_confidence_weight']}")
        print(f"  Thresholds:")
        print(f"    - LLM Invoke Min: {config['thresholds']['llm_invoke_min']}")
        print(f"    - LLM Invoke Max: {config['thresholds']['llm_invoke_max']}")
        print(f"    - Auto Match: {config['thresholds']['auto_match']}")

