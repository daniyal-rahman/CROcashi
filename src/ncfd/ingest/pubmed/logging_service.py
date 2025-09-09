"""
Structured logging service for PubMed pipeline.

Provides consistent logging with context (run_id, trial_id, task_id) and metrics.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from contextvars import ContextVar
from dataclasses import dataclass, asdict

# Context variables for request tracking
run_id_var: ContextVar[Optional[str]] = ContextVar('run_id', default=None)
trial_id_var: ContextVar[Optional[int]] = ContextVar('trial_id', default=None)
task_id_var: ContextVar[Optional[int]] = ContextVar('task_id', default=None)
task_type_var: ContextVar[Optional[str]] = ContextVar('task_type', default=None)


@dataclass
class PipelineMetrics:
    """Metrics for pipeline execution."""
    # Discovery metrics
    documents_discovered: int = 0
    documents_mapped: int = 0
    pmids_found: int = 0
    
    # Processing metrics
    documents_processed: int = 0
    abstracts_fetched: int = 0
    entities_extracted: int = 0
    documents_scored: int = 0
    documents_selected: int = 0
    documents_dropped: int = 0
    
    # OA metrics
    fulltext_retrieved: int = 0
    pmc_found: int = 0
    unpaywall_found: int = 0
    failed_retrievals: int = 0
    
    # Study card metrics
    study_cards_generated: int = 0
    method_cards: int = 0
    results_cards: int = 0
    gates_passed: int = 0
    gates_failed: int = 0
    
    # Queue metrics
    tasks_enqueued: int = 0
    tasks_leased: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_parked: int = 0
    
    # Performance metrics
    execution_time_seconds: float = 0.0
    api_calls_made: int = 0
    rate_limit_delays: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class StructuredLogger:
    """Structured logger with context awareness."""
    
    def __init__(self, name: str, level: int = logging.INFO):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name
            level: Logging level
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Add JSON formatter if not already present
        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _get_context(self) -> Dict[str, Any]:
        """Get current context variables."""
        context = {}
        
        run_id = run_id_var.get()
        if run_id:
            context['run_id'] = run_id
        
        trial_id = trial_id_var.get()
        if trial_id:
            context['trial_id'] = trial_id
        
        task_id = task_id_var.get()
        if task_id:
            context['task_id'] = task_id
        
        task_type = task_type_var.get()
        if task_type:
            context['task_type'] = task_type
        
        return context
    
    def _format_message(self, message: str, extra: Optional[Dict[str, Any]] = None) -> str:
        """
        Format message with context and extra data.
        
        Args:
            message: Log message
            extra: Additional data to include
            
        Returns:
            Formatted message
        """
        context = self._get_context()
        
        if extra:
            context.update(extra)
        
        if context:
            return f"{message} | Context: {json.dumps(context)}"
        else:
            return message
    
    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log info message with context."""
        formatted_message = self._format_message(message, extra)
        self.logger.info(formatted_message)
    
    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log debug message with context."""
        formatted_message = self._format_message(message, extra)
        self.logger.debug(formatted_message)
    
    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log warning message with context."""
        formatted_message = self._format_message(message, extra)
        self.logger.warning(formatted_message)
    
    def error(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log error message with context."""
        formatted_message = self._format_message(message, extra)
        self.logger.error(formatted_message)
    
    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log critical message with context."""
        formatted_message = self._format_message(message, extra)
        self.logger.critical(formatted_message)


class MetricsCollector:
    """Collects and stores pipeline metrics."""
    
    def __init__(self):
        """Initialize metrics collector."""
        self.metrics = PipelineMetrics()
        self.logger = StructuredLogger(__name__)
    
    def reset(self):
        """Reset all metrics to zero."""
        self.metrics = PipelineMetrics()
    
    def increment(self, metric_name: str, value: int = 1):
        """
        Increment a metric.
        
        Args:
            metric_name: Name of the metric
            value: Value to add (default 1)
        """
        if hasattr(self.metrics, metric_name):
            current_value = getattr(self.metrics, metric_name)
            setattr(self.metrics, metric_name, current_value + value)
        else:
            self.logger.warning(f"Unknown metric: {metric_name}")
    
    def set(self, metric_name: str, value: Any):
        """
        Set a metric value.
        
        Args:
            metric_name: Name of the metric
            value: Value to set
        """
        if hasattr(self.metrics, metric_name):
            setattr(self.metrics, metric_name, value)
        else:
            self.logger.warning(f"Unknown metric: {metric_name}")
    
    def get_metrics(self) -> PipelineMetrics:
        """Get current metrics."""
        return self.metrics
    
    def log_metrics(self, stage: str):
        """
        Log current metrics for a stage.
        
        Args:
            stage: Stage name (e.g., 'U1_discovery', 'OA_processing')
        """
        metrics_dict = self.metrics.to_dict()
        self.logger.info(f"Stage {stage} metrics", extra={
            'stage': stage,
            'metrics': metrics_dict
        })


class ContextManager:
    """Manages logging context for pipeline execution."""
    
    def __init__(self, run_id: Optional[str] = None):
        """
        Initialize context manager.
        
        Args:
            run_id: Optional run ID (will generate if not provided)
        """
        self.run_id = run_id or str(uuid.uuid4())
        self.logger = StructuredLogger(__name__)
    
    def set_trial_context(self, trial_id: int):
        """Set trial context."""
        trial_id_var.set(trial_id)
        self.logger.info(f"Set trial context", extra={'trial_id': trial_id})
    
    def set_task_context(self, task_id: int, task_type: str):
        """Set task context."""
        task_id_var.set(task_id)
        task_type_var.set(task_type)
        self.logger.info(f"Set task context", extra={
            'task_id': task_id,
            'task_type': task_type
        })
    
    def clear_context(self):
        """Clear all context variables."""
        run_id_var.set(None)
        trial_id_var.set(None)
        task_id_var.set(None)
        task_type_var.set(None)
    
    def log_stage_start(self, stage: str, **kwargs):
        """Log stage start."""
        self.logger.info(f"Starting stage {stage}", extra={
            'stage': stage,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **kwargs
        })
    
    def log_stage_end(self, stage: str, success: bool, metrics: Optional[PipelineMetrics] = None, **kwargs):
        """Log stage end."""
        extra = {
            'stage': stage,
            'success': success,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **kwargs
        }
        
        if metrics:
            extra['metrics'] = metrics.to_dict()
        
        if success:
            self.logger.info(f"Completed stage {stage}", extra=extra)
        else:
            self.logger.error(f"Failed stage {stage}", extra=extra)
    
    def log_task_start(self, task_type: str, task_id: int, trial_id: int, **kwargs):
        """Log task start."""
        self.set_task_context(task_id, task_type)
        self.set_trial_context(trial_id)
        
        self.logger.info(f"Starting task {task_type}", extra={
            'task_type': task_type,
            'task_id': task_id,
            'trial_id': trial_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **kwargs
        })
    
    def log_task_end(self, task_type: str, task_id: int, trial_id: int, success: bool, **kwargs):
        """Log task end."""
        self.logger.info(f"Completed task {task_type}", extra={
            'task_type': task_type,
            'task_id': task_id,
            'trial_id': trial_id,
            'success': success,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **kwargs
        })
    
    def log_queue_event(self, event_type: str, task_type: str, task_id: Optional[int] = None, **kwargs):
        """Log queue-related events."""
        self.logger.info(f"Queue event: {event_type}", extra={
            'event_type': event_type,
            'task_type': task_type,
            'task_id': task_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **kwargs
        })
    
    def log_api_call(self, service: str, endpoint: str, success: bool, response_time_ms: Optional[float] = None, **kwargs):
        """Log API calls."""
        self.logger.info(f"API call: {service}.{endpoint}", extra={
            'service': service,
            'endpoint': endpoint,
            'success': success,
            'response_time_ms': response_time_ms,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **kwargs
        })
    
    def log_error(self, error_type: str, error_message: str, **kwargs):
        """Log errors with context."""
        self.logger.error(f"Error: {error_type}", extra={
            'error_type': error_type,
            'error_message': error_message,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            **kwargs
        })


# Global instances
context_manager = ContextManager()
metrics_collector = MetricsCollector()


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


def get_context_manager() -> ContextManager:
    """Get the global context manager."""
    return context_manager


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    return metrics_collector
