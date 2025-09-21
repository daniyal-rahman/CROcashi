"""
Centralized Error Handling Utilities

Provides consistent error handling patterns across the entire application.
Eliminates duplication in try/catch blocks and error logging.
"""

import logging
import traceback
from typing import Any, Optional, Callable, Type, Union, Dict
from functools import wraps
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ErrorResult:
    """Standardized error result."""
    success: bool = False
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: Optional[Dict[str, Any]] = None


class ErrorHandler:
    """Centralized error handling with consistent patterns."""
    
    def __init__(self, logger_name: Optional[str] = None):
        """Initialize error handler."""
        self.logger = logging.getLogger(logger_name or __name__)
    
    def handle_database_error(self, error: Exception, operation: str, context: Optional[Dict[str, Any]] = None) -> ErrorResult:
        """Handle database-related errors consistently."""
        error_msg = f"Database error during {operation}: {error}"
        
        # Log with appropriate level based on error type
        if "constraint" in str(error).lower() or "foreign key" in str(error).lower():
            self.logger.error(error_msg)
            self.logger.error(f"Critical database constraint violation: {error}")
        else:
            self.logger.warning(error_msg)
        
        return ErrorResult(
            success=False,
            error_message=error_msg,
            error_type="database_error",
            context=context
        )
    
    def handle_api_error(self, error: Exception, api_name: str, context: Optional[Dict[str, Any]] = None) -> ErrorResult:
        """Handle API-related errors consistently."""
        error_msg = f"API error from {api_name}: {error}"
        self.logger.error(error_msg)
        
        return ErrorResult(
            success=False,
            error_message=error_msg,
            error_type="api_error",
            context=context
        )
    
    def handle_pipeline_error(self, error: Exception, pipeline_name: str, context: Optional[Dict[str, Any]] = None) -> ErrorResult:
        """Handle pipeline-related errors consistently."""
        error_msg = f"Pipeline error in {pipeline_name}: {error}"
        self.logger.error(error_msg)
        
        # Log stack trace for pipeline errors
        self.logger.exception(f"Pipeline {pipeline_name} failed with stack trace")
        
        return ErrorResult(
            success=False,
            error_message=error_msg,
            error_type="pipeline_error",
            context=context
        )
    
    def handle_validation_error(self, error: Exception, validation_type: str, context: Optional[Dict[str, Any]] = None) -> ErrorResult:
        """Handle validation-related errors consistently."""
        error_msg = f"Validation error in {validation_type}: {error}"
        self.logger.warning(error_msg)
        
        return ErrorResult(
            success=False,
            error_message=error_msg,
            error_type="validation_error",
            context=context
        )
    
    def handle_generic_error(self, error: Exception, operation: str, context: Optional[Dict[str, Any]] = None) -> ErrorResult:
        """Handle generic errors consistently."""
        error_msg = f"Error during {operation}: {error}"
        self.logger.error(error_msg)
        
        return ErrorResult(
            success=False,
            error_message=error_msg,
            error_type="generic_error",
            context=context
        )


def safe_execute(
    operation_name: str,
    error_handler: Optional[ErrorHandler] = None,
    default_return: Any = None,
    log_level: str = "error",
    include_traceback: bool = False
):
    """
    Decorator for safe execution with consistent error handling.
    
    Args:
        operation_name: Name of the operation for logging
        error_handler: Custom error handler instance
        default_return: Value to return on error
        log_level: Logging level ('error', 'warning', 'info')
        include_traceback: Whether to include full traceback
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            handler = error_handler or ErrorHandler()
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = f"Error in {operation_name}: {e}"
                
                # Log with appropriate level
                if log_level == "error":
                    handler.logger.error(error_msg)
                elif log_level == "warning":
                    handler.logger.warning(error_msg)
                else:
                    handler.logger.info(error_msg)
                
                # Include traceback if requested
                if include_traceback:
                    handler.logger.exception(f"Full traceback for {operation_name}")
                
                return default_return
        
        return wrapper
    return decorator


def safe_execute_with_result(
    operation_name: str,
    error_handler: Optional[ErrorHandler] = None,
    error_type: str = "generic_error"
):
    """
    Decorator for safe execution that returns ErrorResult on failure.
    
    Args:
        operation_name: Name of the operation for logging
        error_handler: Custom error handler instance
        error_type: Type of error for ErrorResult
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            handler = error_handler or ErrorHandler()
            
            try:
                result = func(*args, **kwargs)
                return ErrorResult(success=True, context={"result": result})
            except Exception as e:
                error_msg = f"Error in {operation_name}: {e}"
                handler.logger.error(error_msg)
                
                return ErrorResult(
                    success=False,
                    error_message=error_msg,
                    error_type=error_type
                )
        
        return wrapper
    return decorator


def handle_database_operation(operation_name: str):
    """Decorator specifically for database operations."""
    return safe_execute(
        operation_name=operation_name,
        default_return=None,
        log_level="warning",
        include_traceback=False
    )


def handle_api_operation(operation_name: str):
    """Decorator specifically for API operations."""
    return safe_execute(
        operation_name=operation_name,
        default_return=None,
        log_level="error",
        include_traceback=True
    )


def handle_pipeline_operation(operation_name: str):
    """Decorator specifically for pipeline operations."""
    return safe_execute(
        operation_name=operation_name,
        default_return=None,
        log_level="error",
        include_traceback=True
    )


class PipelineErrorHandler:
    """Specialized error handler for pipeline operations."""
    
    def __init__(self, pipeline_name: str):
        """Initialize pipeline error handler."""
        self.pipeline_name = pipeline_name
        self.logger = logging.getLogger(f"{__name__}.{pipeline_name}")
        self.error_handler = ErrorHandler(f"{__name__}.{pipeline_name}")
    
    def create_error_output(self, error: Exception, output_class: Type, context: Optional[Dict[str, Any]] = None):
        """Create standardized error output for pipeline results."""
        error_result = self.error_handler.handle_pipeline_error(error, self.pipeline_name, context)
        
        try:
            # Try to create output with error information
            return output_class(
                success=False,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc),
                errors=[error_result.error_message] if error_result.error_message else [str(error)]
            )
        except Exception as e:
            self.logger.error(f"Failed to create error output: {e}")
            return None
    
    def handle_trial_error(self, error: Exception, trial_id: str, context: Optional[Dict[str, Any]] = None):
        """Handle errors specific to trial processing."""
        error_msg = f"Trial processing error for {trial_id}: {error}"
        self.logger.warning(error_msg)
        
        # Log more details for trial errors
        if context:
            self.logger.info(f"Trial context: {context}")
        
        return ErrorResult(
            success=False,
            error_message=error_msg,
            error_type="trial_error",
            context={"trial_id": trial_id, **context} if context else {"trial_id": trial_id}
        )


# Global error handler instance
_error_handler: Optional[ErrorHandler] = None


def get_error_handler(logger_name: Optional[str] = None) -> ErrorHandler:
    """Get global error handler instance."""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler(logger_name)
    return _error_handler


def get_pipeline_error_handler(pipeline_name: str) -> PipelineErrorHandler:
    """Get pipeline-specific error handler."""
    return PipelineErrorHandler(pipeline_name)
