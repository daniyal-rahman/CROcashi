"""
Structured logging for NCFD pipeline.
"""

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional, Dict, Any


def setup_logging(
    level: str = "INFO",
    format_str: Optional[str] = None,
    log_file: Optional[str] = None,
    console: bool = True
) -> logging.Logger:
    """
    Setup structured logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_str: Log format string
        log_file: Path to log file (optional)
        console: Whether to log to console
        
    Returns:
        Configured logger
    """
    # Default format
    if format_str is None:
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Create logger
    logger = logging.getLogger("ncfd")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(format_str)
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Rotating file handler (10MB max, keep 5 files)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "ncfd") -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_trial_event(
    logger: logging.Logger,
    trial_id: str,
    stage: str,
    event: str,
    details: Optional[Dict[str, Any]] = None,
    level: str = "INFO"
):
    """
    Log a trial-specific event with structured data.
    
    Args:
        logger: Logger instance
        trial_id: Trial identifier
        stage: Pipeline stage
        event: Event type
        details: Additional details
        level: Log level
    """
    log_data = {
        "trial_id": trial_id,
        "stage": stage,
        "event": event
    }
    
    if details:
        log_data.update(details)
    
    log_method = getattr(logger, level.lower())
    log_method(f"TRIAL_EVENT: {log_data}")


def log_stage_metrics(
    logger: logging.Logger,
    stage: str,
    metrics: Dict[str, Any],
    level: str = "INFO"
):
    """
    Log stage completion metrics.
    
    Args:
        logger: Logger instance
        stage: Pipeline stage
        metrics: Stage metrics
        level: Log level
    """
    log_method = getattr(logger, level.lower())
    log_method(f"STAGE_METRICS: {stage} - {metrics}")


def log_error_with_context(
    logger: logging.Logger,
    error: Exception,
    context: Dict[str, Any],
    level: str = "ERROR"
):
    """
    Log an error with context information.
    
    Args:
        logger: Logger instance
        error: Exception that occurred
        context: Context information
        level: Log level
    """
    log_method = getattr(logger, level.lower())
    log_method(f"ERROR: {error} - Context: {context}", exc_info=True)
