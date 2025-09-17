"""
Structured logger implementation with comprehensive schema support.

Provides structured logging with JSON output, context management,
and specialized loggers for different operation types.
"""

from __future__ import annotations

import json
import logging
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional, Union
from pathlib import Path

from .schema import LogRecord, LogLevel, LLMLogRecord, DecisionLogRecord, IOTraceRecord
from .context import get_current_context, get_git_info, get_system_info
from .event_taxonomy import EventTaxonomy


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects."""
    
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class StructuredLogger:
    """
    Structured logger with comprehensive schema support.
    
    Automatically includes context variables and enforces log record schema.
    """
    
    def __init__(self, name: str, level: LogLevel = LogLevel.INFO):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name (typically module name)
            level: Log level
        """
        self.name = name
        self.level = level
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, level.value))
        
        # Ensure we have a handler
        if not self._logger.handlers:
            self._setup_handler()
    
    def _setup_handler(self):
        """Setup JSON handler for structured logging."""
        handler = logging.StreamHandler(sys.stdout)
        
        # Use JSON formatter
        formatter = JSONFormatter()
        handler.setFormatter(formatter)
        
        self._logger.addHandler(handler)
    
    def _create_record(
        self,
        level: LogLevel,
        event: str,
        message: Optional[str] = None,
        **kwargs
    ) -> LogRecord:
        """
        Create a structured log record with context.
        
        Args:
            level: Log level
            event: Event name
            message: Human-readable message
            **kwargs: Additional fields
            
        Returns:
            LogRecord instance
        """
        # Get current context
        context = get_current_context()
        
        # Create base record
        record_data = {
            'level': level,
            'module': self.name,
            'event': event,
            'message': message,
            **context,
            **kwargs
        }
        
        return LogRecord(**record_data)
    
    def debug(self, event: str, message: Optional[str] = None, **kwargs):
        """Log debug message."""
        record = self._create_record(LogLevel.DEBUG, event, message, **kwargs)
        self._log_record(record)
    
    def info(self, event: str, message: Optional[str] = None, **kwargs):
        """Log info message."""
        record = self._create_record(LogLevel.INFO, event, message, **kwargs)
        self._log_record(record)
    
    def warn(self, event: str, message: Optional[str] = None, **kwargs):
        """Log warning message."""
        record = self._create_record(LogLevel.WARN, event, message, **kwargs)
        self._log_record(record)
    
    def error(self, event: str, message: Optional[str] = None, **kwargs):
        """Log error message."""
        record = self._create_record(LogLevel.ERROR, event, message, **kwargs)
        self._log_record(record)
    
    def exception(self, event: str, message: Optional[str] = None, **kwargs):
        """Log exception with stack trace."""
        import traceback
        kwargs['stack'] = traceback.format_exc()
        kwargs['err_type'] = kwargs.get('err_type', 'Exception')
        kwargs['err_msg'] = kwargs.get('err_msg', str(kwargs.get('exception', 'Unknown error')))
        
        record = self._create_record(LogLevel.ERROR, event, message, **kwargs)
        self._log_record(record)
    
    def _log_record(self, record: LogRecord):
        """Log a structured record."""
        # Validate event name (disabled to avoid noise from regular logging)
        # if not EventTaxonomy.validate_event(record.event):
        #     self._logger.warning(f"Invalid event name: {record.event}")
        
        # Convert to JSON and log
        log_data = record.to_dict()
        self._logger.info(json.dumps(log_data, ensure_ascii=False, cls=DateTimeEncoder))
    
    def log_llm_call(
        self,
        event: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        usd_cost: float,
        duration_ms: int,
        message: Optional[str] = None,
        **kwargs
    ):
        """Log LLM call with specialized fields."""
        record_data = {
            'level': LogLevel.INFO,
            'module': self.name,
            'event': event,
            'message': message,
            'model': model,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'usd_cost': usd_cost,
            'duration_ms': duration_ms,
            'outcome': 'success',
            **get_current_context(),
            **kwargs
        }
        
        record = LLMLogRecord(**record_data)
        self._log_record(record)
    
    def log_decision(
        self,
        event: str,
        decision: str,
        confidence: float,
        why: str,
        features: Optional[Dict[str, Any]] = None,
        thresholds: Optional[Dict[str, Any]] = None,
        evidence_refs: Optional[list] = None,
        message: Optional[str] = None,
        **kwargs
    ):
        """Log decision with transparency fields."""
        record_data = {
            'level': LogLevel.INFO,
            'module': self.name,
            'event': event,
            'message': message,
            'decision': decision,
            'confidence': confidence,
            'why': why,
            'features': features,
            'thresholds': thresholds,
            'evidence_refs': evidence_refs,
            'outcome': 'success',
            **get_current_context(),
            **kwargs
        }
        
        record = DecisionLogRecord(**record_data)
        self._log_record(record)
    
    def log_error_with_context(
        self,
        event: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        **kwargs
    ):
        """Log error with full context and stack trace."""
        import traceback
        
        record_data = {
            'level': LogLevel.ERROR,
            'module': self.name,
            'event': event,
            'message': message or f"Error in {self.name}: {str(error)}",
            'err_type': type(error).__name__,
            'err_msg': str(error),
            'stack': traceback.format_exc(),
            'outcome': 'fail',
            **get_current_context(),
            **(context or {}),
            **kwargs
        }
        
        record = LogRecord(**record_data)
        self._log_record(record)
    
    def log_performance(
        self,
        event: str,
        duration_ms: int,
        processed_n: Optional[int] = None,
        success_n: Optional[int] = None,
        fail_n: Optional[int] = None,
        message: Optional[str] = None,
        **kwargs
    ):
        """Log performance metrics."""
        record_data = {
            'level': LogLevel.INFO,
            'module': self.name,
            'event': event,
            'message': message,
            'duration_ms': duration_ms,
            'processed_n': processed_n,
            'success_n': success_n,
            'fail_n': fail_n,
            'outcome': 'success',
            **get_current_context(),
            **kwargs
        }
        
        record = LogRecord(**record_data)
        self._log_record(record)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record):
        """Format log record as JSON."""
        if isinstance(record.msg, dict):
            # Already structured
            return json.dumps(record.msg, ensure_ascii=False)
        else:
            # Convert to structured format
            log_data = {
                'ts': datetime.utcnow().isoformat() + 'Z',
                'level': record.levelname,
                'module': record.name,
                'event': getattr(record, 'event', 'log.message'),
                'message': record.getMessage(),
            }
            
            # Add any extra fields
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                              'filename', 'module', 'lineno', 'funcName', 'created', 
                              'msecs', 'relativeCreated', 'thread', 'threadName', 
                              'processName', 'process', 'getMessage']:
                    log_data[key] = value
            
            return json.dumps(log_data, ensure_ascii=False)


# Global logger registry
_loggers: Dict[str, StructuredLogger] = {}


def get_logger(name: str = "ncfd") -> StructuredLogger:
    """
    Get or create a structured logger.
    
    Args:
        name: Logger name (typically module name)
        
    Returns:
        StructuredLogger instance
    """
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name)
    return _loggers[name]


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    console: bool = True,
    json_format: bool = True
) -> StructuredLogger:
    """
    Setup structured logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (optional)
        console: Whether to log to console
        json_format: Whether to use JSON format
        
    Returns:
        Root logger instance
    """
    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        if json_format:
            console_handler.setFormatter(JSONFormatter())
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        if json_format:
            file_handler.setFormatter(JSONFormatter())
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Get system info for context
    system_info = get_system_info()
    git_info = get_git_info()
    
    # Set global context
    from .context import (
        ctx_code_version, ctx_git_dirty, ctx_py_version, ctx_env
    )
    
    ctx_code_version.set(git_info['code_version'])
    ctx_git_dirty.set(git_info['git_dirty'])
    ctx_py_version.set(system_info['py_version'])
    ctx_env.set(os.getenv('ENV', 'dev'))
    
    return get_logger("ncfd")
