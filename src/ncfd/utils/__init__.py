"""
Utility modules for NCFD.

Provides centralized utilities for configuration management, error handling,
and other common functionality to eliminate duplication across the codebase.
"""

from .config_manager import ConfigManager, get_config_manager, get_config, get_config_value
from .error_handler import (
    ErrorHandler, ErrorResult, PipelineErrorHandler,
    safe_execute, safe_execute_with_result,
    handle_database_operation, handle_api_operation, handle_pipeline_operation,
    get_error_handler, get_pipeline_error_handler
)

__all__ = [
    # Config management
    'ConfigManager', 'get_config_manager', 'get_config', 'get_config_value',
    
    # Error handling
    'ErrorHandler', 'ErrorResult', 'PipelineErrorHandler',
    'safe_execute', 'safe_execute_with_result',
    'handle_database_operation', 'handle_api_operation', 'handle_pipeline_operation',
    'get_error_handler', 'get_pipeline_error_handler'
]