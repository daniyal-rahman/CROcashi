"""
JSON Parsing Monitoring and Error Tracking

Provides comprehensive monitoring and error tracking for LLM JSON parsing issues.
"""

import logging
import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class ParsingErrorType(Enum):
    """Types of JSON parsing errors."""
    JSON_DECODE_ERROR = "json_decode_error"
    MISSING_FIELDS = "missing_fields"
    INVALID_VALUE_TYPE = "invalid_value_type"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"
    NUMBER_CONVERSION_ERROR = "number_conversion_error"
    UNKNOWN_FIELD = "unknown_field"


@dataclass
class ParsingError:
    """Record of a JSON parsing error."""
    error_type: ParsingErrorType
    error_message: str
    field_name: Optional[str] = None
    original_value: Optional[Any] = None
    converted_value: Optional[Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


@dataclass
class ParsingStats:
    """Statistics for JSON parsing performance."""
    total_attempts: int = 0
    successful_parses: int = 0
    failed_parses: int = 0
    errors_by_type: Dict[str, int] = None
    conversion_successes: int = 0
    conversion_failures: int = 0
    avg_parse_time_ms: float = 0.0
    
    def __post_init__(self):
        if self.errors_by_type is None:
            self.errors_by_type = {}


class JSONParsingMonitor:
    """Monitors and tracks JSON parsing performance and errors."""
    
    def __init__(self, log_level: str = "INFO"):
        self.stats = ParsingStats()
        self.recent_errors: List[ParsingError] = []
        self.max_error_history = 100
        self.logger = logging.getLogger(f"{__name__}.monitor")
        
        # Set up logging level
        level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(level)
    
    def record_parsing_attempt(self, success: bool, parse_time_ms: float, 
                             errors: Optional[List[ParsingError]] = None):
        """Record a parsing attempt."""
        self.stats.total_attempts += 1
        
        if success:
            self.stats.successful_parses += 1
        else:
            self.stats.failed_parses += 1
        
        # Update average parse time
        if self.stats.total_attempts == 1:
            self.stats.avg_parse_time_ms = parse_time_ms
        else:
            # Running average
            self.stats.avg_parse_time_ms = (
                (self.stats.avg_parse_time_ms * (self.stats.total_attempts - 1) + parse_time_ms) 
                / self.stats.total_attempts
            )
        
        # Record errors
        if errors:
            for error in errors:
                self._record_error(error)
    
    def record_conversion_attempt(self, success: bool, original_value: Any, 
                                converted_value: Any = None):
        """Record a value conversion attempt."""
        if success:
            self.stats.conversion_successes += 1
        else:
            self.stats.conversion_failures += 1
    
    def _record_error(self, error: ParsingError):
        """Record an error."""
        error_type_str = error.error_type.value
        self.stats.errors_by_type[error_type_str] = self.stats.errors_by_type.get(error_type_str, 0) + 1
        
        # Add to recent errors
        self.recent_errors.append(error)
        if len(self.recent_errors) > self.max_error_history:
            self.recent_errors.pop(0)
        
        # Log the error
        self.logger.warning(f"JSON parsing error: {error.error_type.value} - {error.error_message}")
        if error.field_name:
            self.logger.warning(f"  Field: {error.field_name}")
        if error.original_value is not None:
            self.logger.warning(f"  Original value: {error.original_value}")
        if error.converted_value is not None:
            self.logger.warning(f"  Converted value: {error.converted_value}")
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """Get a summary of parsing statistics."""
        success_rate = 0.0
        if self.stats.total_attempts > 0:
            success_rate = self.stats.successful_parses / self.stats.total_attempts
        
        conversion_success_rate = 0.0
        total_conversions = self.stats.conversion_successes + self.stats.conversion_failures
        if total_conversions > 0:
            conversion_success_rate = self.stats.conversion_successes / total_conversions
        
        return {
            "total_attempts": self.stats.total_attempts,
            "success_rate": success_rate,
            "avg_parse_time_ms": self.stats.avg_parse_time_ms,
            "conversion_success_rate": conversion_success_rate,
            "errors_by_type": self.stats.errors_by_type.copy(),
            "recent_error_count": len(self.recent_errors)
        }
    
    def get_recent_errors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent errors as dictionaries."""
        recent = self.recent_errors[-limit:] if limit else self.recent_errors
        return [asdict(error) for error in recent]
    
    def log_performance_summary(self):
        """Log a performance summary."""
        summary = self.get_stats_summary()
        
        self.logger.info("=== JSON Parsing Performance Summary ===")
        self.logger.info(f"Total attempts: {summary['total_attempts']}")
        self.logger.info(f"Success rate: {summary['success_rate']:.2%}")
        self.logger.info(f"Average parse time: {summary['avg_parse_time_ms']:.2f}ms")
        self.logger.info(f"Conversion success rate: {summary['conversion_success_rate']:.2%}")
        
        if summary['errors_by_type']:
            self.logger.info("Errors by type:")
            for error_type, count in summary['errors_by_type'].items():
                self.logger.info(f"  {error_type}: {count}")
        
        if summary['recent_error_count'] > 0:
            self.logger.info(f"Recent errors: {summary['recent_error_count']}")
    
    def reset_stats(self):
        """Reset all statistics."""
        self.stats = ParsingStats()
        self.recent_errors.clear()
        self.logger.info("JSON parsing statistics reset")


# Global monitor instance
_global_monitor = JSONParsingMonitor()


def get_global_monitor() -> JSONParsingMonitor:
    """Get the global JSON parsing monitor."""
    return _global_monitor


def log_parsing_error(error_type: ParsingErrorType, error_message: str, 
                     field_name: Optional[str] = None, original_value: Optional[Any] = None,
                     converted_value: Optional[Any] = None):
    """Log a parsing error to the global monitor."""
    error = ParsingError(
        error_type=error_type,
        error_message=error_message,
        field_name=field_name,
        original_value=original_value,
        converted_value=converted_value
    )
    _global_monitor._record_error(error)


def log_parsing_attempt(success: bool, parse_time_ms: float, errors: Optional[List[ParsingError]] = None):
    """Log a parsing attempt to the global monitor."""
    _global_monitor.record_parsing_attempt(success, parse_time_ms, errors)


def log_conversion_attempt(success: bool, original_value: Any, converted_value: Any = None):
    """Log a conversion attempt to the global monitor."""
    _global_monitor.record_conversion_attempt(success, original_value, converted_value)


def get_parsing_stats() -> Dict[str, Any]:
    """Get parsing statistics from the global monitor."""
    return _global_monitor.get_stats_summary()


def log_performance_summary():
    """Log performance summary from the global monitor."""
    _global_monitor.log_performance_summary()


# Context manager for timing parsing operations
class ParsingTimer:
    """Context manager for timing JSON parsing operations."""
    
    def __init__(self, operation_name: str = "json_parsing"):
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        parse_time_ms = (self.end_time - self.start_time) * 1000
        
        # Log the timing
        logger.debug(f"{self.operation_name} took {parse_time_ms:.2f}ms")
        
        # Record in global monitor
        success = exc_type is None
        log_parsing_attempt(success, parse_time_ms)


# Example usage and testing
if __name__ == "__main__":
    # Test the monitoring system
    monitor = JSONParsingMonitor()
    
    # Simulate some parsing attempts
    with ParsingTimer("test_parsing"):
        time.sleep(0.01)  # Simulate parsing time
        monitor.record_parsing_attempt(True, 10.0)
    
    # Simulate an error
    error = ParsingError(
        error_type=ParsingErrorType.NUMBER_CONVERSION_ERROR,
        error_message="Could not convert 'ninetyFive' to number",
        field_name="confidence",
        original_value="ninetyFive",
        converted_value=0.95
    )
    monitor._record_error(error)
    
    # Log performance summary
    monitor.log_performance_summary()
    
    # Get stats
    stats = monitor.get_stats_summary()
    print(f"Stats: {stats}")
