"""
Legacy logging module - DEPRECATED.

This module is deprecated in favor of the new structured logging system.
Use ncfd.logging instead for all new code.

The new system provides:
- Structured logging with comprehensive schema
- Canonical event taxonomy
- IO tracing decorators
- Context management
- LLM-specific logging
- Decision transparency logging
"""

import warnings
from typing import Optional, Dict, Any

# Import new structured logging system
from .logging import get_logger as get_structured_logger, setup_logging as setup_structured_logging
from .logging import LogContext, set_context
from .logging import EventTaxonomy
from .logging import io_trace, llm_trace, parse_trace, validate_trace

# Issue deprecation warning
warnings.warn(
    "ncfd.logging module is deprecated. Use ncfd.logging.structured_logger instead.",
    DeprecationWarning,
    stacklevel=2
)


def setup_logging(
    level: str = "INFO",
    format_str: Optional[str] = None,
    log_file: Optional[str] = None,
    console: bool = True
):
    """
    DEPRECATED: Use ncfd.logging.setup_logging instead.
    
    Setup structured logging for the application.
    """
    warnings.warn(
        "setup_logging is deprecated. Use ncfd.logging.setup_logging instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    return setup_structured_logging(
        level=level,
        log_file=log_file,
        console=console,
        json_format=True
    )


def get_logger(name: str = "ncfd"):
    """
    DEPRECATED: Use ncfd.logging.get_logger instead.
    
    Get a logger instance.
    """
    warnings.warn(
        "get_logger is deprecated. Use ncfd.logging.get_logger instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    return get_structured_logger(name)


def log_trial_event(
    logger,
    trial_id: str,
    stage: str,
    event: str,
    details: Optional[Dict[str, Any]] = None,
    level: str = "INFO"
):
    """
    DEPRECATED: Use structured logger methods instead.
    
    Log a trial-specific event with structured data.
    """
    warnings.warn(
        "log_trial_event is deprecated. Use structured logger methods instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Convert to new format
    kwargs = details or {}
    kwargs.update({
        'trial_id': trial_id,
        'stage': stage
    })
    
    log_method = getattr(logger, level.lower())
    log_method(event, **kwargs)


def log_stage_metrics(
    logger,
    stage: str,
    metrics: Dict[str, Any],
    level: str = "INFO"
):
    """
    DEPRECATED: Use structured logger methods instead.
    
    Log stage completion metrics.
    """
    warnings.warn(
        "log_stage_metrics is deprecated. Use structured logger methods instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Convert to new format
    kwargs = metrics.copy()
    kwargs['stage'] = stage
    
    log_method = getattr(logger, level.lower())
    log_method(EventTaxonomy.STAGE_SUMMARY, **kwargs)


def log_error_with_context(
    logger,
    error: Exception,
    context: Dict[str, Any],
    level: str = "ERROR"
):
    """
    DEPRECATED: Use structured logger methods instead.
    
    Log an error with context information.
    """
    warnings.warn(
        "log_error_with_context is deprecated. Use structured logger methods instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Use new error logging method
    logger.log_error_with_context(
        EventTaxonomy.ERROR_CRITICAL,
        error,
        context=context
    )
