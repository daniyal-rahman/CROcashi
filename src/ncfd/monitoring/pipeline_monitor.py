"""
Comprehensive Pipeline Monitoring and Alerting System for CROcashi.

This module provides:
- Pipeline execution monitoring
- Data quality monitoring
- Performance tracking
- Alert generation and management
- Resource monitoring
"""

from __future__ import annotations

import logging
import time
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

from ..quality.data_quality import DataQualityFramework, QualityMetrics

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class AlertStatus(Enum):
    """Alert status."""
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"


class AlertType(Enum):
    """Alert types."""
    PIPELINE_FAILURE = "pipeline_failure"
    QUALITY_DEGRADATION = "quality_degradation"
    PERFORMANCE_ISSUE = "performance_issue"
    RESOURCE_CRITICAL = "resource_critical"
    DATA_FRESHNESS = "data_freshness"
    ERROR_RATE_HIGH = "error_rate_high"
    SUCCESS_RATE_LOW = "success_rate_low"


@dataclass
class PipelineMetrics:
    """Pipeline execution metrics."""
    pipeline_name: str
    execution_id: str
    
    # Execution metrics
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    success: bool = False
    
    # Throughput metrics
    records_processed: int = 0
    records_successful: int = 0
    records_failed: int = 0
    processing_rate: float = 0.0  # records per second
    
    # Error metrics
    error_count: int = 0
    error_rate: float = 0.0
    last_error: Optional[str] = None
    
    # Resource metrics
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    disk_usage_percent: float = 0.0
    
    # Quality metrics
    quality_score: float = 0.0
    validation_passed: int = 0
    validation_failed: int = 0
    
    def __post_init__(self):
        """Calculate derived metrics."""
        if self.end_time:
            self.duration_seconds = (self.end_time - self.start_time).total_seconds()
            
            if self.duration_seconds > 0:
                self.processing_rate = self.records_processed / self.duration_seconds
        
        if self.records_processed > 0:
            self.error_rate = self.error_count / self.records_processed


@dataclass
class SystemMetrics:
    """System resource metrics."""
    timestamp: datetime
    
    # CPU metrics
    cpu_percent: float
    cpu_count: int
    cpu_freq_mhz: float
    
    # Memory metrics
    memory_total_gb: float
    memory_available_gb: float
    memory_used_gb: float
    memory_percent: float
    
    # Disk metrics
    disk_total_gb: float
    disk_used_gb: float
    disk_free_gb: float
    disk_percent: float
    
    # Network metrics
    network_bytes_sent: int
    network_bytes_recv: int
    
    # Process metrics
    process_count: int
    thread_count: int


@dataclass
class Alert:
    """Alert definition."""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    
    # Alert details
    source: str
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    
    # Alert metadata
    created_at: datetime
    status: AlertStatus = AlertStatus.ACTIVE
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[DateTime] = None
    acknowledged_by: Optional[str] = None
    
    # Alert context
    context: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Set created_at to current time."""
        if not self.created_at:
            self.created_at = datetime.utcnow()


class PipelineMonitor:
    """
    Comprehensive pipeline monitoring and alerting system.
    
    Features:
    - Real-time pipeline monitoring
    - Data quality tracking
    - Performance monitoring
    - Resource monitoring
    - Alert generation and management
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the pipeline monitor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize data quality framework
        self.quality_framework = DataQualityFramework(config.get('data_quality', {}))
        
        # Monitoring state
        self.monitoring_enabled = config.get('monitoring', {}).get('enable_monitoring', True)
        self.monitoring_interval = config.get('monitoring', {}).get('monitoring_interval_seconds', 300)
        
        # Metrics storage
        self.pipeline_metrics: List[PipelineMetrics] = []
        self.system_metrics: List[SystemMetrics] = []
        self.quality_metrics: List[QualityMetrics] = []
        
        # Alert management
        self.active_alerts: List[Alert] = []
        self.alert_history: List[Alert] = []
        self.alert_thresholds = config.get('monitoring', {}).get('alert_thresholds', {})
        
        # Monitoring state
        self.last_monitoring_run = None
        self.monitoring_running = False
        
        # Configuration
        self.enable_resource_monitoring = config.get('monitoring', {}).get('track_resource_usage', True)
        self.enable_performance_monitoring = config.get('monitoring', {}).get('track_performance_metrics', True)
        self.enable_quality_monitoring = config.get('monitoring', {}).get('track_quality_metrics', True)
        
        # Alert channels
        self.alert_channels = config.get('alerting', {}).get('alert_channels', ['log'])
        
        self.logger.info("Pipeline Monitor initialized")
    
    def start_monitoring(self):
        """Start the monitoring system."""
        if not self.monitoring_enabled:
            self.logger.info("Monitoring is disabled")
            return
        
        if self.monitoring_running:
            self.logger.warning("Monitoring is already running")
            return
        
        self.monitoring_running = True
        self.logger.info("Pipeline monitoring started")
        
        # TODO: Implement background monitoring thread
        # For now, monitoring is manual via update_metrics()
    
    def stop_monitoring(self):
        """Stop the monitoring system."""
        if not self.monitoring_running:
            self.logger.warning("Monitoring is not running")
            return
        
        self.monitoring_running = False
        self.logger.info("Pipeline monitoring stopped")
    
    def update_pipeline_metrics(self, pipeline_name: str, execution_id: str, **kwargs) -> PipelineMetrics:
        """Update pipeline execution metrics."""
        # Find existing metrics or create new ones
        metrics = None
        for m in self.pipeline_metrics:
            if m.pipeline_name == pipeline_name and m.execution_id == execution_id:
                metrics = m
                break
        
        if not metrics:
            metrics = PipelineMetrics(
                pipeline_name=pipeline_name,
                execution_id=execution_id,
                start_time=datetime.utcnow()
            )
            self.pipeline_metrics.append(metrics)
        
        # Update metrics
        for key, value in kwargs.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)
        
        # Update end time and calculate duration if execution is complete
        if 'success' in kwargs and kwargs['success'] is not None:
            metrics.end_time = datetime.utcnow()
            metrics.duration_seconds = (metrics.end_time - metrics.start_time).total_seconds()
            
            if metrics.duration_seconds > 0:
                metrics.processing_rate = metrics.records_processed / metrics.duration_seconds
        
        # Calculate error rate
        if metrics.records_processed > 0:
            metrics.error_rate = metrics.error_count / metrics.records_processed
        
        # Check for alerts
        self._check_pipeline_alerts(metrics)
        
        return metrics
    
    def update_system_metrics(self):
        """Update system resource metrics."""
        if not self.enable_resource_monitoring:
            return
        
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            cpu_freq_mhz = cpu_freq.current if cpu_freq else 0
            
            # Memory metrics
            memory = psutil.virtual_memory()
            memory_total_gb = memory.total / (1024**3)
            memory_available_gb = memory.available / (1024**3)
            memory_used_gb = memory.used / (1024**3)
            memory_percent = memory.percent
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_total_gb = disk.total / (1024**3)
            disk_used_gb = disk.used / (1024**3)
            disk_free_gb = disk.free / (1024**3)
            disk_percent = disk.percent
            
            # Network metrics
            network = psutil.net_io_counters()
            network_bytes_sent = network.bytes_sent
            network_bytes_recv = network.bytes_recv
            
            # Process metrics
            process_count = len(psutil.pids())
            thread_count = sum(p.num_threads() for p in psutil.process_iter(['num_threads']) if p.info['num_threads'])
            
            # Create system metrics
            system_metrics = SystemMetrics(
                timestamp=datetime.utcnow(),
                cpu_percent=cpu_percent,
                cpu_count=cpu_count,
                cpu_freq_mhz=cpu_freq_mhz,
                memory_total_gb=memory_total_gb,
                memory_available_gb=memory_available_gb,
                memory_used_gb=memory_used_gb,
                memory_percent=memory_percent,
                disk_total_gb=disk_total_gb,
                disk_used_gb=disk_used_gb,
                disk_free_gb=disk_free_gb,
                disk_percent=disk_percent,
                network_bytes_sent=network_bytes_sent,
                network_bytes_recv=network_bytes_recv,
                process_count=process_count,
                thread_count=thread_count
            )
            
            self.system_metrics.append(system_metrics)
            
            # Check for resource alerts
            self._check_resource_alerts(system_metrics)
            
            # Limit storage
            if len(self.system_metrics) > 1000:
                self.system_metrics = self.system_metrics[-1000:]
            
        except Exception as e:
            self.logger.error(f"Error updating system metrics: {e}")
    
    def update_quality_metrics(self, quality_metrics: QualityMetrics):
        """Update data quality metrics."""
        if not self.enable_quality_monitoring:
            return
        
        self.quality_metrics.append(quality_metrics)
        
        # Check for quality alerts
        self._check_quality_alerts(quality_metrics)
        
        # Limit storage
        if len(self.quality_metrics) > 1000:
            self.quality_metrics = self.quality_metrics[-1000:]
    
    def _check_pipeline_alerts(self, metrics: PipelineMetrics):
        """Check for pipeline-related alerts."""
        # Check for pipeline failures
        if not metrics.success:
            self._create_alert(
                alert_type=AlertType.PIPELINE_FAILURE,
                severity=AlertSeverity.CRITICAL,
                title=f"Pipeline {metrics.pipeline_name} Failed",
                message=f"Pipeline execution {metrics.execution_id} failed after {metrics.duration_seconds:.1f}s",
                source=metrics.pipeline_name,
                entity_id=metrics.execution_id,
                entity_type="pipeline_execution",
                context={
                    "duration_seconds": metrics.duration_seconds,
                    "records_processed": metrics.records_processed,
                    "error_count": metrics.error_count,
                    "last_error": metrics.last_error
                }
            )
        
        # Check for high error rates
        error_rate_threshold = self.alert_thresholds.get('error_rate_above', 0.1)
        if metrics.error_rate > error_rate_threshold:
            self._create_alert(
                alert_type=AlertType.ERROR_RATE_HIGH,
                severity=AlertSeverity.HIGH,
                title=f"High Error Rate in {metrics.pipeline_name}",
                message=f"Error rate {metrics.error_rate:.1%} exceeds threshold {error_rate_threshold:.1%}",
                source=metrics.pipeline_name,
                entity_id=metrics.execution_id,
                entity_type="pipeline_execution",
                context={
                    "error_rate": metrics.error_rate,
                    "threshold": error_rate_threshold,
                    "records_processed": metrics.records_processed,
                    "error_count": metrics.error_count
                }
            )
        
        # Check for slow execution
        slow_execution_threshold = self.alert_thresholds.get('slow_execution_threshold_minutes', 60)
        if metrics.duration_seconds > (slow_execution_threshold * 60):
            self._create_alert(
                alert_type=AlertType.PERFORMANCE_ISSUE,
                severity=AlertSeverity.MEDIUM,
                title=f"Slow Pipeline Execution: {metrics.pipeline_name}",
                message=f"Pipeline execution took {metrics.duration_seconds/60:.1f} minutes",
                source=metrics.pipeline_name,
                entity_id=metrics.execution_id,
                entity_type="pipeline_execution",
                context={
                    "duration_minutes": metrics.duration_seconds / 60,
                    "threshold_minutes": slow_execution_threshold,
                    "records_processed": metrics.records_processed,
                    "processing_rate": metrics.processing_rate
                }
            )
    
    def _check_resource_alerts(self, metrics: SystemMetrics):
        """Check for resource-related alerts."""
        # Check memory usage
        memory_threshold = self.alert_thresholds.get('memory_usage_above', 0.8)
        if metrics.memory_percent > (memory_threshold * 100):
            self._create_alert(
                alert_type=AlertType.RESOURCE_CRITICAL,
                severity=AlertSeverity.HIGH,
                title="High Memory Usage",
                message=f"Memory usage {metrics.memory_percent:.1f}% exceeds threshold {memory_threshold*100:.1f}%",
                source="system_monitor",
                context={
                    "memory_percent": metrics.memory_percent,
                    "memory_used_gb": metrics.memory_used_gb,
                    "memory_available_gb": metrics.memory_available_gb,
                    "threshold_percent": memory_threshold * 100
                }
            )
        
        # Check disk usage
        disk_threshold = self.alert_thresholds.get('disk_usage_above', 0.9)
        if metrics.disk_percent > (disk_threshold * 100):
            self._create_alert(
                alert_type=AlertType.RESOURCE_CRITICAL,
                severity=AlertSeverity.CRITICAL,
                title="Critical Disk Usage",
                message=f"Disk usage {metrics.disk_percent:.1f}% exceeds threshold {disk_threshold*100:.1f}%",
                source="system_monitor",
                context={
                    "disk_percent": metrics.disk_percent,
                    "disk_used_gb": metrics.disk_used_gb,
                    "disk_free_gb": metrics.disk_free_gb,
                    "threshold_percent": disk_threshold * 100
                }
            )
    
    def _check_quality_alerts(self, metrics: QualityMetrics):
        """Check for quality-related alerts."""
        # Check overall quality score
        quality_threshold = self.alert_thresholds.get('quality_score_below', 0.6)
        if metrics.overall_quality_score < quality_threshold:
            self._create_alert(
                alert_type=AlertType.QUALITY_DEGRADATION,
                severity=AlertSeverity.MEDIUM,
                title="Data Quality Degradation",
                message=f"Quality score {metrics.overall_quality_score:.2f} below threshold {quality_threshold:.2f}",
                source="quality_monitor",
                context={
                    "quality_score": metrics.overall_quality_score,
                    "threshold": quality_threshold,
                    "total_records": metrics.total_records,
                    "failed_validations": metrics.failed_validations,
                    "critical_issues": metrics.critical_issues,
                    "high_issues": metrics.high_issues
                }
            )
        
        # Check for critical issues
        critical_threshold = self.alert_thresholds.get('critical_issues_above', 0)
        if metrics.critical_issues > critical_threshold:
            self._create_alert(
                alert_type=AlertType.QUALITY_DEGRADATION,
                severity=AlertSeverity.CRITICAL,
                title="Critical Data Quality Issues",
                message=f"Critical issues: {metrics.critical_issues} (threshold: {critical_threshold})",
                source="quality_monitor",
                context={
                    "critical_issues": metrics.critical_issues,
                    "threshold": critical_threshold,
                    "total_records": metrics.total_records,
                    "overall_quality_score": metrics.overall_quality_score
                }
            )
    
    def _create_alert(self, alert_type: AlertType, severity: AlertSeverity, title: str, 
                      message: str, source: str, entity_id: Optional[str] = None, 
                      entity_type: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        """Create a new alert."""
        alert_id = f"{alert_type.value}_{int(time.time())}"
        
        alert = Alert(
            alert_id=alert_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            source=source,
            entity_id=entity_id,
            entity_type=entity_type,
            context=context or {}
        )
        
        self.active_alerts.append(alert)
        self.alert_history.append(alert)
        
        # Send alert through configured channels
        self._send_alert(alert)
        
        self.logger.warning(f"Alert created: {title} ({severity.value})")
        
        # Limit alert history
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]
    
    def _send_alert(self, alert: Alert):
        """Send alert through configured channels."""
        for channel in self.alert_channels:
            try:
                if channel == "log":
                    self._send_log_alert(alert)
                elif channel == "email":
                    self._send_email_alert(alert)
                elif channel == "slack":
                    self._send_slack_alert(alert)
                elif channel == "webhook":
                    self._send_webhook_alert(alert)
                else:
                    self.logger.warning(f"Unknown alert channel: {channel}")
                    
            except Exception as e:
                self.logger.error(f"Error sending alert through {channel}: {e}")
    
    def _send_log_alert(self, alert: Alert):
        """Send alert to log."""
        log_message = f"ALERT [{alert.severity.value}] {alert.title}: {alert.message}"
        if alert.context:
            log_message += f" Context: {alert.context}"
        
        if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH]:
            self.logger.error(log_message)
        elif alert.severity == AlertSeverity.MEDIUM:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)
    
    def _send_email_alert(self, alert: Alert):
        """Send alert via email (placeholder)."""
        # TODO: Implement email alerting
        self.logger.info(f"Email alert would be sent: {alert.title}")
    
    def _send_slack_alert(self, alert: Alert):
        """Send alert via Slack (placeholder)."""
        # TODO: Implement Slack alerting
        self.logger.info(f"Slack alert would be sent: {alert.title}")
    
    def _send_webhook_alert(self, alert: Alert):
        """Send alert via webhook (placeholder)."""
        # TODO: Implement webhook alerting
        self.logger.info(f"Webhook alert would be sent: {alert.title}")
    
    def acknowledge_alert(self, alert_id: str, acknowledged_by: str):
        """Acknowledge an alert."""
        for alert in self.active_alerts:
            if alert.alert_id == alert_id:
                alert.status = AlertStatus.ACKNOWLEDGED
                alert.acknowledged_at = datetime.utcnow()
                alert.acknowledged_by = acknowledged_by
                
                # Move to history
                self.active_alerts.remove(alert)
                
                self.logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
                return
        
        self.logger.warning(f"Alert {alert_id} not found")
    
    def resolve_alert(self, alert_id: str, resolved_by: str):
        """Resolve an alert."""
        for alert in self.alert_history:
            if alert.alert_id == alert_id:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.utcnow()
                
                self.logger.info(f"Alert {alert_id} resolved by {resolved_by}")
                return
        
        self.logger.warning(f"Alert {alert_id} not found")
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status."""
        return {
            'monitoring_enabled': self.monitoring_enabled,
            'monitoring_running': self.monitoring_running,
            'last_monitoring_run': self.last_monitoring_run.isoformat() if self.last_monitoring_run else None,
            'monitoring_interval_seconds': self.monitoring_interval,
            
            # Metrics summary
            'pipeline_metrics_count': len(self.pipeline_metrics),
            'system_metrics_count': len(self.system_metrics),
            'quality_metrics_count': len(self.quality_metrics),
            
            # Alert summary
            'active_alerts_count': len(self.active_alerts),
            'alert_history_count': len(self.alert_history),
            
            # Configuration
            'resource_monitoring_enabled': self.enable_resource_monitoring,
            'performance_monitoring_enabled': self.enable_performance_monitoring,
            'quality_monitoring_enabled': self.enable_quality_monitoring,
            'alert_channels': self.alert_channels
        }
    
    def get_pipeline_performance_summary(self, pipeline_name: Optional[str] = None, 
                                       days: int = 7) -> Dict[str, Any]:
        """Get pipeline performance summary."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        if pipeline_name:
            metrics = [m for m in self.pipeline_metrics 
                      if m.pipeline_name == pipeline_name and m.start_time >= cutoff_date]
        else:
            metrics = [m for m in self.pipeline_metrics if m.start_time >= cutoff_date]
        
        if not metrics:
            return {"error": "No metrics available for the specified period"}
        
        # Calculate summary statistics
        total_executions = len(metrics)
        successful_executions = len([m for m in metrics if m.success])
        failed_executions = total_executions - successful_executions
        
        avg_duration = sum(m.duration_seconds for m in metrics) / total_executions
        avg_processing_rate = sum(m.processing_rate for m in metrics if m.processing_rate > 0) / total_executions
        
        total_records = sum(m.records_processed for m in metrics)
        total_errors = sum(m.error_count for m in metrics)
        overall_error_rate = total_errors / total_records if total_records > 0 else 0
        
        return {
            'period_days': days,
            'pipeline_name': pipeline_name or 'all',
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': failed_executions,
            'success_rate': successful_executions / total_executions if total_executions > 0 else 0,
            
            'avg_duration_seconds': avg_duration,
            'avg_processing_rate': avg_processing_rate,
            'total_records_processed': total_records,
            'total_errors': total_errors,
            'overall_error_rate': overall_error_rate
        }
    
    def get_system_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get system performance summary."""
        cutoff_date = datetime.utcnow() - timedelta(hours=hours)
        recent_metrics = [m for m in self.system_metrics if m.timestamp >= cutoff_date]
        
        if not recent_metrics:
            return {"error": "No system metrics available for the specified period"}
        
        # Calculate summary statistics
        avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
        avg_memory = sum(m.memory_percent for m in recent_metrics) / len(recent_metrics)
        avg_disk = sum(m.disk_percent for m in recent_metrics) / len(recent_metrics)
        
        max_cpu = max(m.cpu_percent for m in recent_metrics)
        max_memory = max(m.memory_percent for m in recent_metrics)
        max_disk = max(m.disk_percent for m in recent_metrics)
        
        return {
            'period_hours': hours,
            'metrics_count': len(recent_metrics),
            
            'cpu_usage': {
                'average_percent': avg_cpu,
                'maximum_percent': max_cpu,
                'current_percent': recent_metrics[-1].cpu_percent if recent_metrics else 0
            },
            
            'memory_usage': {
                'average_percent': avg_memory,
                'maximum_percent': max_memory,
                'current_percent': recent_metrics[-1].memory_percent if recent_metrics else 0,
                'current_available_gb': recent_metrics[-1].memory_available_gb if recent_metrics else 0
            },
            
            'disk_usage': {
                'average_percent': avg_disk,
                'maximum_percent': max_disk,
                'current_percent': recent_metrics[-1].disk_percent if recent_metrics else 0,
                'current_free_gb': recent_metrics[-1].disk_free_gb if recent_metrics else 0
            }
        }
    
    def get_quality_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get data quality summary."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        recent_metrics = [m for m in self.quality_metrics if m.calculated_at >= cutoff_date]
        
        if not recent_metrics:
            return {"error": "No quality metrics available for the specified period"}
        
        # Calculate summary statistics
        avg_quality_score = sum(m.overall_quality_score for m in recent_metrics) / len(recent_metrics)
        avg_completeness = sum(m.completeness_score for m in recent_metrics) / len(recent_metrics)
        
        total_records = sum(m.total_records for m in recent_metrics)
        total_failures = sum(m.failed_validations for m in recent_metrics)
        total_critical = sum(m.critical_issues for m in recent_metrics)
        total_high = sum(m.high_issues for m in recent_metrics)
        
        return {
            'period_days': days,
            'datasets_count': len(recent_metrics),
            
            'quality_scores': {
                'average_overall_score': avg_quality_score,
                'average_completeness_score': avg_completeness,
                'current_overall_score': recent_metrics[-1].overall_quality_score if recent_metrics else 0
            },
            
            'validation_results': {
                'total_records': total_records,
                'total_failures': total_failures,
                'overall_failure_rate': total_failures / total_records if total_records > 0 else 0
            },
            
            'issue_summary': {
                'total_critical_issues': total_critical,
                'total_high_issues': total_high,
                'current_critical_issues': recent_metrics[-1].critical_issues if recent_metrics else 0,
                'current_high_issues': recent_metrics[-1].high_issues if recent_metrics else 0
            }
        }
    
    def generate_monitoring_report(self, format: str = "json") -> str:
        """Generate a comprehensive monitoring report."""
        report_data = {
            'report_generated_at': datetime.utcnow().isoformat(),
            'monitoring_status': self.get_monitoring_status(),
            'pipeline_performance': self.get_pipeline_performance_summary(),
            'system_performance': self.get_system_performance_summary(),
            'data_quality': self.get_quality_summary(),
            'active_alerts': [
                {
                    'alert_id': alert.alert_id,
                    'type': alert.alert_type.value,
                    'severity': alert.severity.value,
                    'title': alert.title,
                    'message': alert.message,
                    'source': alert.source,
                    'created_at': alert.created_at.isoformat()
                }
                for alert in self.active_alerts
            ]
        }
        
        if format == "json":
            return json.dumps(report_data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported report format: {format}")
    
    def clear_old_metrics(self, keep_days: int = 30):
        """Clear old metrics to free storage."""
        cutoff_date = datetime.utcnow() - timedelta(days=keep_days)
        
        # Clear old pipeline metrics
        old_pipeline_count = len([m for m in self.pipeline_metrics if m.start_time < cutoff_date])
        self.pipeline_metrics = [m for m in self.pipeline_metrics if m.start_time >= cutoff_date]
        
        # Clear old system metrics
        old_system_count = len([m for m in self.system_metrics if m.timestamp < cutoff_date])
        self.system_metrics = [m for m in self.system_metrics if m.timestamp >= cutoff_date]
        
        # Clear old quality metrics
        old_quality_count = len([m for m in self.quality_metrics if m.calculated_at < cutoff_date])
        self.quality_metrics = [m for m in self.quality_metrics if m.calculated_at >= cutoff_date]
        
        self.logger.info(f"Cleared old metrics: {old_pipeline_count} pipeline, {old_system_count} system, {old_quality_count} quality")
    
    def export_metrics(self, format: str = "json") -> str:
        """Export all metrics in specified format."""
        export_data = {
            'exported_at': datetime.utcnow().isoformat(),
            'pipeline_metrics': [vars(m) for m in self.pipeline_metrics[-100:]],  # Last 100
            'system_metrics': [vars(m) for m in self.system_metrics[-100:]],      # Last 100
            'quality_metrics': [vars(m) for m in self.quality_metrics[-100:]],    # Last 100
            'active_alerts': [vars(a) for a in self.active_alerts],
            'alert_history': [vars(a) for a in self.alert_history[-100:]]        # Last 100
        }
        
        if format == "json":
            return json.dumps(export_data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")
