"""
PubMed API Monitoring - Rate limit monitoring and alerting.

Provides comprehensive monitoring of PubMed API usage, rate limits,
and performance metrics with alerting capabilities.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class RateLimitAlert:
    """Represents a rate limit alert."""
    timestamp: datetime
    level: AlertLevel
    message: str
    component: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class APIMetrics:
    """API usage metrics."""
    timestamp: datetime
    total_requests: int
    successful_requests: int
    failed_requests: int
    rate_limit_hits: int
    avg_response_time: float
    queue_size: int
    active_requests: int


class PubMedMonitor:
    """Monitors PubMed API usage and rate limits."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the monitor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.alerts: List[RateLimitAlert] = []
        self.metrics_history: List[APIMetrics] = []
        self.alert_thresholds = {
            'rate_limit_hits_per_minute': 5,
            'consecutive_failures': 3,
            'queue_size': 100,
            'avg_response_time': 10.0,
            'error_rate': 0.1  # 10% error rate
        }
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        logger.info("PubMed Monitor initialized")
    
    async def start_monitoring(self):
        """Start the monitoring task."""
        if not self._monitoring:
            self._monitoring = True
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info("PubMed monitoring started")
    
    async def stop_monitoring(self):
        """Stop the monitoring task."""
        if self._monitoring:
            self._monitoring = False
            if self._monitor_task:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
            logger.info("PubMed monitoring stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._monitoring:
            try:
                await self._check_rate_limits()
                await self._check_performance()
                await self._check_queue_health()
                
                # Clean up old metrics and alerts
                await self._cleanup_old_data()
                
                # Wait before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _check_rate_limits(self):
        """Check for rate limit violations."""
        try:
            # Get current metrics
            current_metrics = await self._get_current_metrics()
            
            # Check rate limit hits
            if current_metrics.rate_limit_hits > self.alert_thresholds['rate_limit_hits_per_minute']:
                await self._create_alert(
                    AlertLevel.WARNING,
                    f"High rate limit hits: {current_metrics.rate_limit_hits} in last minute",
                    "rate_limit_monitor",
                    {"rate_limit_hits": current_metrics.rate_limit_hits}
                )
            
            # Check consecutive failures
            if current_metrics.failed_requests > self.alert_thresholds['consecutive_failures']:
                await self._create_alert(
                    AlertLevel.ERROR,
                    f"Consecutive failures: {current_metrics.failed_requests}",
                    "rate_limit_monitor",
                    {"consecutive_failures": current_metrics.failed_requests}
                )
            
        except Exception as e:
            logger.error(f"Error checking rate limits: {e}")
    
    async def _check_performance(self):
        """Check API performance metrics."""
        try:
            current_metrics = await self._get_current_metrics()
            
            # Check response time
            if current_metrics.avg_response_time > self.alert_thresholds['avg_response_time']:
                await self._create_alert(
                    AlertLevel.WARNING,
                    f"High response time: {current_metrics.avg_response_time:.2f}s",
                    "performance_monitor",
                    {"avg_response_time": current_metrics.avg_response_time}
                )
            
            # Check error rate
            if current_metrics.total_requests > 0:
                error_rate = current_metrics.failed_requests / current_metrics.total_requests
                if error_rate > self.alert_thresholds['error_rate']:
                    await self._create_alert(
                        AlertLevel.ERROR,
                        f"High error rate: {error_rate:.2%}",
                        "performance_monitor",
                        {"error_rate": error_rate}
                    )
            
        except Exception as e:
            logger.error(f"Error checking performance: {e}")
    
    async def _check_queue_health(self):
        """Check queue health."""
        try:
            current_metrics = await self._get_current_metrics()
            
            # Check queue size
            if current_metrics.queue_size > self.alert_thresholds['queue_size']:
                await self._create_alert(
                    AlertLevel.WARNING,
                    f"Large queue size: {current_metrics.queue_size}",
                    "queue_monitor",
                    {"queue_size": current_metrics.queue_size}
                )
            
        except Exception as e:
            logger.error(f"Error checking queue health: {e}")
    
    async def _get_current_metrics(self) -> APIMetrics:
        """Get current API metrics."""
        # This would integrate with the actual client manager and request queue
        # For now, return placeholder metrics
        return APIMetrics(
            timestamp=datetime.now(timezone.utc),
            total_requests=0,
            successful_requests=0,
            failed_requests=0,
            rate_limit_hits=0,
            avg_response_time=0.0,
            queue_size=0,
            active_requests=0
        )
    
    async def _create_alert(self, level: AlertLevel, message: str, component: str, details: Dict[str, Any]):
        """Create a new alert."""
        alert = RateLimitAlert(
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=message,
            component=component,
            details=details
        )
        
        self.alerts.append(alert)
        
        # Log the alert
        log_level = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.ERROR: logging.ERROR,
            AlertLevel.CRITICAL: logging.CRITICAL
        }[level]
        
        logger.log(log_level, f"ALERT [{level.value}] {component}: {message}")
        
        # Keep only recent alerts
        if len(self.alerts) > 1000:
            self.alerts = self.alerts[-500:]
    
    async def _cleanup_old_data(self):
        """Clean up old metrics and alerts."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        
        # Clean up old metrics
        self.metrics_history = [
            m for m in self.metrics_history 
            if m.timestamp > cutoff_time
        ]
        
        # Clean up old alerts
        self.alerts = [
            a for a in self.alerts 
            if a.timestamp > cutoff_time
        ]
    
    def get_recent_alerts(self, hours: int = 1) -> List[RateLimitAlert]:
        """Get recent alerts."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [a for a in self.alerts if a.timestamp > cutoff_time]
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        if not self.metrics_history:
            return {"status": "no_data"}
        
        recent_metrics = self.metrics_history[-10:]  # Last 10 data points
        
        return {
            "total_requests": sum(m.total_requests for m in recent_metrics),
            "successful_requests": sum(m.successful_requests for m in recent_metrics),
            "failed_requests": sum(m.failed_requests for m in recent_metrics),
            "rate_limit_hits": sum(m.rate_limit_hits for m in recent_metrics),
            "avg_response_time": sum(m.avg_response_time for m in recent_metrics) / len(recent_metrics),
            "max_queue_size": max(m.queue_size for m in recent_metrics),
            "alerts_count": len(self.get_recent_alerts(1)),
            "monitoring_status": "active" if self._monitoring else "inactive"
        }
    
    def export_metrics(self, filepath: str):
        """Export metrics to JSON file."""
        data = {
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": [
                {
                    "timestamp": m.timestamp.isoformat(),
                    "total_requests": m.total_requests,
                    "successful_requests": m.successful_requests,
                    "failed_requests": m.failed_requests,
                    "rate_limit_hits": m.rate_limit_hits,
                    "avg_response_time": m.avg_response_time,
                    "queue_size": m.queue_size,
                    "active_requests": m.active_requests
                }
                for m in self.metrics_history
            ],
            "alerts": [
                {
                    "timestamp": a.timestamp.isoformat(),
                    "level": a.level.value,
                    "message": a.message,
                    "component": a.component,
                    "details": a.details
                }
                for a in self.alerts
            ]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Metrics exported to {filepath}")


# Global instance
_monitor: Optional[PubMedMonitor] = None


def get_monitor(config: Optional[Dict[str, Any]] = None) -> PubMedMonitor:
    """Get the global monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = PubMedMonitor(config)
    return _monitor


async def start_monitoring(config: Optional[Dict[str, Any]] = None):
    """Start monitoring."""
    monitor = get_monitor(config)
    await monitor.start_monitoring()


async def stop_monitoring():
    """Stop monitoring."""
    monitor = get_monitor()
    await monitor.stop_monitoring()
