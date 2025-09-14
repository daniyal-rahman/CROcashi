"""
Comprehensive structured logging system for NCFD pipeline.

This module provides:
- Structured logging with required schema fields
- Canonical event taxonomy for all pipeline stages
- IO tracing decorator for boundary logging
- Error handling with actionable context
- Reproducibility tracking
- LLM-specific logging with cost tracking
"""

from .structured_logger import StructuredLogger, get_logger
from .event_taxonomy import EventTaxonomy
from .io_trace import io_trace
from .context import LogContext, set_context
from .schema import LogRecord, LogLevel

__all__ = [
    "StructuredLogger",
    "get_logger", 
    "EventTaxonomy",
    "io_trace",
    "LogContext",
    "set_context",
    "LogRecord",
    "LogLevel"
]
