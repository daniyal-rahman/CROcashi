"""
Unit tests for the Pipeline Monitoring and Alerting System.

Tests all monitoring capabilities, alert generation, metrics collection, and reporting.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

from src.ncfd.monitoring.pipeline_monitor import (
    PipelineMonitor, PipelineMetrics, SystemMetrics, Alert,
    AlertSeverity, AlertStatus, AlertType
)
from src.ncfd.quality.data_quality import QualityMetrics


class TestPipelineMetrics:
    """Test PipelineMetrics class."""
    
    def test_pipeline_metrics_creation(self):
        """Test creating pipeline metrics."""
        start_time = datetime.utcnow()
        metrics = PipelineMetrics(
            pipeline_name="test_pipeline",
            execution_id="test_exec_123",
            start_time=start_time
        )
        
        assert metrics.pipeline_name == "test_pipeline"
        assert metrics.execution_id == "test_exec_123"
        assert metrics.start_time == start_time
        assert metrics.end_time is None
        assert metrics.duration_seconds == 0.0
        assert metrics.success is False
    
    def test_pipeline_metrics_calculation(self):
        """Test pipeline metrics calculation."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(seconds=10)
        
        metrics = PipelineMetrics(
            pipeline_name="test_pipeline",
            execution_id="test_exec_123",
            start_time=start_time,
            end_time=end_time,
            records_processed=100,
            records_successful=90,
            records_failed=10,
            error_count=10
        )
        
        assert metrics.duration_seconds == 10.0
        assert metrics.processing_rate == 10.0  # 100 records / 10 seconds
        assert metrics.error_rate == 0.1  # 10 errors / 100 records
    
    def test_pipeline_metrics_no_duration(self):
        """Test pipeline metrics with no duration."""
        start_time = datetime.utcnow()
        metrics = PipelineMetrics(
            pipeline_name="test_pipeline",
            execution_id="test_exec_123",
            start_time=start_time,
            records_processed=100,
            error_count=5
        )
        
        assert metrics.duration_seconds == 0.0
        assert metrics.processing_rate == 0.0
        assert metrics.error_rate == 0.05  # 5 errors / 100 records


class TestSystemMetrics:
    """Test SystemMetrics class."""
    
    def test_system_metrics_creation(self):
        """Test creating system metrics."""
        timestamp = datetime.utcnow()
        metrics = SystemMetrics(
            timestamp=timestamp,
            cpu_percent=25.5,
            cpu_count=8,
            cpu_freq_mhz=2400.0,
            memory_total_gb=16.0,
            memory_available_gb=8.0,
            memory_used_gb=8.0,
            memory_percent=50.0,
            disk_total_gb=1000.0,
            disk_used_gb=500.0,
            disk_free_gb=500.0,
            disk_percent=50.0,
            network_bytes_sent=1000000,
            network_bytes_recv=2000000,
            process_count=150,
            thread_count=300
        )
        
        assert metrics.timestamp == timestamp
        assert metrics.cpu_percent == 25.5
        assert metrics.memory_percent == 50.0
        assert metrics.disk_percent == 50.0


class TestAlert:
    """Test Alert class."""
    
    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            alert_id="test_alert_123",
            alert_type=AlertType.PIPELINE_FAILURE,
            severity=AlertSeverity.CRITICAL,
            title="Test Alert",
            message="Test alert message",
            source="test_source"
        )
        
        assert alert.alert_id == "test_alert_123"
        assert alert.alert_type == AlertType.PIPELINE_FAILURE
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.title == "Test Alert"
        assert alert.message == "Test alert message"
        assert alert.source == "test_source"
        assert alert.status == AlertStatus.ACTIVE
        assert alert.created_at is not None
    
    def test_alert_with_context(self):
        """Test creating an alert with context."""
        context = {"field": "value", "count": 42}
        alert = Alert(
            alert_id="test_alert_123",
            alert_type=AlertType.QUALITY_DEGRADATION,
            severity=AlertSeverity.HIGH,
            title="Test Alert",
            message="Test alert message",
            source="test_source",
            entity_id="test_entity",
            entity_type="test_type",
            context=context
        )
        
        assert alert.entity_id == "test_entity"
        assert alert.entity_type == "test_type"
        assert alert.context == context


class TestPipelineMonitor:
    """Test PipelineMonitor class."""
    
    @pytest.fixture
    def monitor(self):
        """Create a test monitor instance."""
        config = {
            'monitoring': {
                'enable_monitoring': True,
                'monitoring_interval_seconds': 300,
                'track_resource_usage': True,
                'track_performance_metrics': True,
                'track_quality_metrics': True,
                'alert_thresholds': {
                    'error_rate_above': 0.1,
                    'slow_execution_threshold_minutes': 60,
                    'memory_usage_above': 0.8,
                    'disk_usage_above': 0.9,
                    'quality_score_below': 0.6,
                    'critical_issues_above': 0
                }
            },
            'alerting': {
                'alert_channels': ['log']
            },
            'data_quality': {
                'min_quality_score': 0.6,
                'max_error_rate': 0.05
            }
        }
        return PipelineMonitor(config)
    
    def test_monitor_initialization(self, monitor):
        """Test monitor initialization."""
        assert monitor.monitoring_enabled is True
        assert monitor.monitoring_interval == 300
        assert monitor.enable_resource_monitoring is True
        assert monitor.enable_performance_monitoring is True
        assert monitor.enable_quality_monitoring is True
        assert 'log' in monitor.alert_channels
    
    def test_start_stop_monitoring(self, monitor):
        """Test starting and stopping monitoring."""
        assert monitor.monitoring_running is False
        
        monitor.start_monitoring()
        assert monitor.monitoring_running is True
        
        monitor.stop_monitoring()
        assert monitor.monitoring_running is False
    
    def test_update_pipeline_metrics(self, monitor):
        """Test updating pipeline metrics."""
        execution_id = "test_exec_123"
        
        # Create initial metrics
        metrics = monitor.update_pipeline_metrics(
            "test_pipeline",
            execution_id,
            records_processed=100,
            records_successful=90,
            records_failed=10,
            error_count=10
        )
        
        assert metrics.pipeline_name == "test_pipeline"
        assert metrics.execution_id == execution_id
        assert metrics.records_processed == 100
        assert metrics.records_successful == 90
        assert metrics.records_failed == 10
        assert metrics.error_count == 10
        assert metrics.error_rate == 0.1
        
        # Update metrics
        updated_metrics = monitor.update_pipeline_metrics(
            "test_pipeline",
            execution_id,
            success=True,
            end_time=datetime.utcnow()
        )
        
        assert updated_metrics.success is True
        assert updated_metrics.end_time is not None
        assert updated_metrics.duration_seconds > 0
        assert updated_metrics.processing_rate > 0
    
    @patch('psutil.cpu_percent')
    @patch('psutil.cpu_count')
    @patch('psutil.cpu_freq')
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_usage')
    @patch('psutil.net_io_counters')
    @patch('psutil.process_iter')
    @patch('psutil.pids')
    def test_update_system_metrics(self, mock_pids, mock_process_iter, 
                                  mock_net_io, mock_disk, mock_memory, 
                                  mock_cpu_freq, mock_cpu_count, mock_cpu_percent):
        """Test updating system metrics."""
        # Mock psutil responses
        mock_cpu_percent.return_value = 25.5
        mock_cpu_count.return_value = 8
        mock_cpu_freq.return_value = Mock(current=2400.0)
        
        mock_memory = Mock()
        mock_memory.total = 16 * (1024**3)  # 16GB
        mock_memory.available = 8 * (1024**3)  # 8GB
        mock_memory.used = 8 * (1024**3)  # 8GB
        mock_memory.percent = 50.0
        mock_virtual_memory.return_value = mock_memory
        
        mock_disk.return_value = Mock(
            total=1000 * (1024**3),  # 1000GB
            used=500 * (1024**3),    # 500GB
            free=500 * (1024**3)     # 500GB
        )
        
        mock_net_io.return_value = Mock(
            bytes_sent=1000000,
            bytes_recv=2000000
        )
        
        mock_pids.return_value = list(range(150))
        mock_process_iter.return_value = [Mock(info={'num_threads': 2}) for _ in range(150)]
        
        monitor = PipelineMonitor({
            'monitoring': {
                'enable_monitoring': True,
                'track_resource_usage': True,
                'alert_thresholds': {}
            },
            'alerting': {'alert_channels': ['log']},
            'data_quality': {}
        })
        
        monitor.update_system_metrics()
        
        assert len(monitor.system_metrics) == 1
        metrics = monitor.system_metrics[0]
        
        assert metrics.cpu_percent == 25.5
        assert metrics.cpu_count == 8
        assert metrics.memory_percent == 50.0
        assert metrics.disk_percent == 50.0
    
    def test_update_quality_metrics(self, monitor):
        """Test updating quality metrics."""
        quality_metrics = QualityMetrics(
            dataset_name="test_dataset",
            total_records=100,
            validated_records=95,
            passed_validations=80,
            failed_validations=15,
            warning_validations=5
        )
        
        monitor.update_quality_metrics(quality_metrics)
        
        assert len(monitor.quality_metrics) == 1
        assert monitor.quality_metrics[0] == quality_metrics
    
    def test_pipeline_failure_alert(self, monitor):
        """Test alert generation for pipeline failure."""
        metrics = PipelineMetrics(
            pipeline_name="test_pipeline",
            execution_id="test_exec_123",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            success=False,
            records_processed=100,
            error_count=20,
            last_error="Test error"
        )
        
        monitor._check_pipeline_alerts(metrics)
        
        # Check that alert was created
        assert len(monitor.active_alerts) == 1
        alert = monitor.active_alerts[0]
        
        assert alert.alert_type == AlertType.PIPELINE_FAILURE
        assert alert.severity == AlertSeverity.CRITICAL
        assert "Pipeline test_pipeline Failed" in alert.title
        assert alert.source == "test_pipeline"
    
    def test_high_error_rate_alert(self, monitor):
        """Test alert generation for high error rate."""
        metrics = PipelineMetrics(
            pipeline_name="test_pipeline",
            execution_id="test_exec_123",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            success=True,
            records_processed=100,
            error_count=15,  # 15% error rate
            last_error="Test error"
        )
        
        monitor._check_pipeline_alerts(metrics)
        
        # Check that alert was created
        assert len(monitor.active_alerts) == 1
        alert = monitor.active_alerts[0]
        
        assert alert.alert_type == AlertType.ERROR_RATE_HIGH
        assert alert.severity == AlertSeverity.HIGH
        assert "High Error Rate" in alert.title
        assert alert.context["error_rate"] == 0.15
    
    def test_slow_execution_alert(self, monitor):
        """Test alert generation for slow execution."""
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(minutes=90)  # 90 minutes
        
        metrics = PipelineMetrics(
            pipeline_name="test_pipeline",
            execution_id="test_exec_123",
            start_time=start_time,
            end_time=end_time,
            success=True,
            records_processed=1000
        )
        
        monitor._check_pipeline_alerts(metrics)
        
        # Check that alert was created
        assert len(monitor.active_alerts) == 1
        alert = monitor.active_alerts[0]
        
        assert alert.alert_type == AlertType.PERFORMANCE_ISSUE
        assert alert.severity == AlertSeverity.MEDIUM
        assert "Slow Pipeline Execution" in alert.title
        assert alert.context["duration_minutes"] > 60
    
    def test_resource_alerts(self, monitor):
        """Test alert generation for resource issues."""
        # Test high memory usage
        memory_metrics = SystemMetrics(
            timestamp=datetime.utcnow(),
            cpu_percent=25.0,
            cpu_count=8,
            cpu_freq_mhz=2400.0,
            memory_total_gb=16.0,
            memory_available_gb=1.0,
            memory_used_gb=15.0,
            memory_percent=85.0,  # Above 80% threshold
            disk_total_gb=1000.0,
            disk_used_gb=500.0,
            disk_free_gb=500.0,
            disk_percent=50.0,
            network_bytes_sent=1000000,
            network_bytes_recv=2000000,
            process_count=150,
            thread_count=300
        )
        
        monitor._check_resource_alerts(memory_metrics)
        
        # Check that memory alert was created
        assert len(monitor.active_alerts) == 1
        alert = monitor.active_alerts[0]
        
        assert alert.alert_type == AlertType.RESOURCE_CRITICAL
        assert alert.severity == AlertSeverity.HIGH
        assert "High Memory Usage" in alert.title
        
        # Test critical disk usage
        disk_metrics = SystemMetrics(
            timestamp=datetime.utcnow(),
            cpu_percent=25.0,
            cpu_count=8,
            cpu_freq_mhz=2400.0,
            memory_total_gb=16.0,
            memory_available_gb=8.0,
            memory_used_gb=8.0,
            memory_percent=50.0,
            disk_total_gb=1000.0,
            disk_used_gb=950.0,
            disk_free_gb=50.0,
            disk_percent=95.0,  # Above 90% threshold
            network_bytes_sent=1000000,
            network_bytes_recv=2000000,
            process_count=150,
            thread_count=300
        )
        
        monitor._check_resource_alerts(disk_metrics)
        
        # Check that disk alert was created
        assert len(monitor.active_alerts) == 2
        disk_alert = monitor.active_alerts[1]
        
        assert disk_alert.alert_type == AlertType.RESOURCE_CRITICAL
        assert disk_alert.severity == AlertSeverity.CRITICAL
        assert "Critical Disk Usage" in disk_alert.title
    
    def test_quality_alerts(self, monitor):
        """Test alert generation for quality issues."""
        # Test low quality score
        quality_metrics = QualityMetrics(
            dataset_name="test_dataset",
            total_records=100,
            validated_records=100,
            passed_validations=50,  # 50% pass rate
            failed_validations=50
        )
        
        monitor._check_quality_alerts(quality_metrics)
        
        # Check that quality alert was created
        assert len(monitor.active_alerts) == 1
        alert = monitor.active_alerts[0]
        
        assert alert.alert_type == AlertType.QUALITY_DEGRADATION
        assert alert.severity == AlertSeverity.MEDIUM
        assert "Data Quality Degradation" in alert.title
        
        # Test critical issues
        critical_metrics = QualityMetrics(
            dataset_name="test_dataset",
            total_records=100,
            validated_records=100,
            passed_validations=80,
            failed_validations=20,
            critical_issues=5  # Above 0 threshold
        )
        
        monitor._check_quality_alerts(critical_metrics)
        
        # Check that critical issues alert was created
        assert len(monitor.active_alerts) == 2
        critical_alert = monitor.active_alerts[1]
        
        assert critical_alert.alert_type == AlertType.QUALITY_DEGRADATION
        assert critical_alert.severity == AlertSeverity.CRITICAL
        assert "Critical Data Quality Issues" in critical_alert.title
    
    def test_alert_acknowledgment(self, monitor):
        """Test alert acknowledgment."""
        # Create an alert
        alert = Alert(
            alert_id="test_alert_123",
            alert_type=AlertType.PIPELINE_FAILURE,
            severity=AlertSeverity.CRITICAL,
            title="Test Alert",
            message="Test alert message",
            source="test_source"
        )
        monitor.active_alerts.append(alert)
        
        # Acknowledge alert
        monitor.acknowledge_alert("test_alert_123", "test_user")
        
        # Check that alert was moved to history
        assert len(monitor.active_alerts) == 0
        assert len(monitor.alert_history) == 1
        
        # Check alert status
        history_alert = monitor.alert_history[0]
        assert history_alert.status == AlertStatus.ACKNOWLEDGED
        assert history_alert.acknowledged_by == "test_user"
        assert history_alert.acknowledged_at is not None
    
    def test_alert_resolution(self, monitor):
        """Test alert resolution."""
        # Create an alert in history
        alert = Alert(
            alert_id="test_alert_123",
            alert_type=AlertType.PIPELINE_FAILURE,
            severity=AlertSeverity.CRITICAL,
            title="Test Alert",
            message="Test alert message",
            source="test_source"
        )
        monitor.alert_history.append(alert)
        
        # Resolve alert
        monitor.resolve_alert("test_alert_123", "test_user")
        
        # Check alert status
        resolved_alert = monitor.alert_history[0]
        assert resolved_alert.status == AlertStatus.RESOLVED
        assert resolved_alert.resolved_at is not None
    
    def test_get_monitoring_status(self, monitor):
        """Test getting monitoring status."""
        status = monitor.get_monitoring_status()
        
        assert 'monitoring_enabled' in status
        assert 'monitoring_running' in status
        assert 'pipeline_metrics_count' in status
        assert 'system_metrics_count' in status
        assert 'quality_metrics_count' in status
        assert 'active_alerts_count' in status
        assert 'alert_history_count' in status
    
    def test_get_pipeline_performance_summary(self, monitor):
        """Test getting pipeline performance summary."""
        # Add some test metrics
        for i in range(5):
            start_time = datetime.utcnow() - timedelta(days=i)
            end_time = start_time + timedelta(minutes=30)
            
            metrics = PipelineMetrics(
                pipeline_name="test_pipeline",
                execution_id=f"exec_{i}",
                start_time=start_time,
                end_time=end_time,
                success=i < 4,  # 4 successful, 1 failed
                records_processed=100,
                records_successful=90,
                records_failed=10,
                error_count=10
            )
            monitor.pipeline_metrics.append(metrics)
        
        summary = monitor.get_pipeline_performance_summary(days=7)
        
        assert summary['period_days'] == 7
        assert summary['pipeline_name'] == 'all'
        assert summary['total_executions'] == 5
        assert summary['successful_executions'] == 4
        assert summary['failed_executions'] == 1
        assert summary['success_rate'] == 0.8
    
    def test_get_system_performance_summary(self, monitor):
        """Test getting system performance summary."""
        # Add some test metrics
        for i in range(24):  # 24 hours
            timestamp = datetime.utcnow() - timedelta(hours=i)
            
            metrics = SystemMetrics(
                timestamp=timestamp,
                cpu_percent=25.0 + i,
                cpu_count=8,
                cpu_freq_mhz=2400.0,
                memory_total_gb=16.0,
                memory_available_gb=8.0,
                memory_used_gb=8.0,
                memory_percent=50.0 + i,
                disk_total_gb=1000.0,
                disk_used_gb=500.0,
                disk_free_gb=500.0,
                disk_percent=50.0,
                network_bytes_sent=1000000,
                network_bytes_recv=2000000,
                process_count=150,
                thread_count=300
            )
            monitor.system_metrics.append(metrics)
        
        summary = monitor.get_system_performance_summary(hours=24)
        
        assert summary['period_hours'] == 24
        assert summary['metrics_count'] == 24
        assert 'cpu_usage' in summary
        assert 'memory_usage' in summary
        assert 'disk_usage' in summary
    
    def test_get_quality_summary(self, monitor):
        """Test getting quality summary."""
        # Add some test metrics
        for i in range(7):  # 7 days
            calculated_at = datetime.utcnow() - timedelta(days=i)
            
            metrics = QualityMetrics(
                dataset_name=f"dataset_{i}",
                total_records=100,
                validated_records=100,
                passed_validations=80 + i,
                failed_validations=20 - i
            )
            metrics.calculated_at = calculated_at
            monitor.quality_metrics.append(metrics)
        
        summary = monitor.get_quality_summary(days=7)
        
        assert summary['period_days'] == 7
        assert summary['datasets_count'] == 7
        assert 'quality_scores' in summary
        assert 'validation_results' in summary
        assert 'issue_summary' in summary
    
    def test_generate_monitoring_report(self, monitor):
        """Test generating monitoring report."""
        report = monitor.generate_monitoring_report()
        
        # Parse JSON report
        report_data = json.loads(report)
        
        assert 'report_generated_at' in report_data
        assert 'monitoring_status' in report_data
        assert 'pipeline_performance' in report_data
        assert 'system_performance' in report_data
        assert 'data_quality' in report_data
        assert 'active_alerts' in report_data
    
    def test_export_metrics(self, monitor):
        """Test exporting metrics."""
        # Add some test data
        metrics = PipelineMetrics(
            pipeline_name="test_pipeline",
            execution_id="test_exec",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            success=True,
            records_processed=100
        )
        monitor.pipeline_metrics.append(metrics)
        
        export = monitor.export_metrics()
        
        # Parse JSON export
        export_data = json.loads(export)
        
        assert 'exported_at' in export_data
        assert 'pipeline_metrics' in export_data
        assert 'system_metrics' in export_data
        assert 'quality_metrics' in export_data
        assert 'active_alerts' in export_data
        assert 'alert_history' in export_data
    
    def test_clear_old_metrics(self, monitor):
        """Test clearing old metrics."""
        # Add old metrics
        old_date = datetime.utcnow() - timedelta(days=40)
        new_date = datetime.utcnow() - timedelta(days=5)
        
        # Old pipeline metrics
        old_metrics = PipelineMetrics(
            pipeline_name="old_pipeline",
            execution_id="old_exec",
            start_time=old_date
        )
        monitor.pipeline_metrics.append(old_metrics)
        
        # New pipeline metrics
        new_metrics = PipelineMetrics(
            pipeline_name="new_pipeline",
            execution_id="new_exec",
            start_time=new_date
        )
        monitor.pipeline_metrics.append(new_metrics)
        
        # Clear old metrics
        monitor.clear_old_metrics(keep_days=30)
        
        # Check that only new metrics remain
        assert len(monitor.pipeline_metrics) == 1
        assert monitor.pipeline_metrics[0].pipeline_name == "new_pipeline"


class TestPipelineMonitorIntegration:
    """Integration tests for the pipeline monitor."""
    
    @pytest.fixture
    def monitor(self):
        """Create a test monitor instance."""
        config = {
            'monitoring': {
                'enable_monitoring': True,
                'track_resource_usage': True,
                'track_performance_metrics': True,
                'track_quality_metrics': True,
                'alert_thresholds': {
                    'error_rate_above': 0.1,
                    'slow_execution_threshold_minutes': 60,
                    'memory_usage_above': 0.8,
                    'disk_usage_above': 0.9,
                    'quality_score_below': 0.6,
                    'critical_issues_above': 0
                }
            },
            'alerting': {'alert_channels': ['log']},
            'data_quality': {}
        }
        return PipelineMonitor(config)
    
    def test_end_to_end_monitoring_workflow(self, monitor):
        """Test complete monitoring workflow."""
        # Start monitoring
        monitor.start_monitoring()
        
        # Update pipeline metrics
        execution_id = "test_exec_123"
        metrics = monitor.update_pipeline_metrics(
            "test_pipeline",
            execution_id,
            records_processed=100,
            records_successful=90,
            records_failed=10,
            error_count=10
        )
        
        # Update system metrics
        monitor.update_system_metrics()
        
        # Update quality metrics
        quality_metrics = QualityMetrics(
            dataset_name="test_dataset",
            total_records=100,
            validated_records=100,
            passed_validations=80,
            failed_validations=20
        )
        monitor.update_quality_metrics(quality_metrics)
        
        # Check that metrics were collected
        assert len(monitor.pipeline_metrics) == 1
        assert len(monitor.system_metrics) == 1
        assert len(monitor.quality_metrics) == 1
        
        # Check that alerts were generated
        assert len(monitor.active_alerts) > 0
        
        # Generate report
        report = monitor.generate_monitoring_report()
        assert "report_generated_at" in report
        
        # Stop monitoring
        monitor.stop_monitoring()
        assert monitor.monitoring_running is False
    
    def test_alert_lifecycle(self, monitor):
        """Test complete alert lifecycle."""
        # Create alert through pipeline failure
        metrics = PipelineMetrics(
            pipeline_name="test_pipeline",
            execution_id="test_exec_123",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            success=False,
            records_processed=100,
            error_count=20
        )
        
        monitor._check_pipeline_alerts(metrics)
        
        # Check alert created
        assert len(monitor.active_alerts) == 1
        alert_id = monitor.active_alerts[0].alert_id
        
        # Acknowledge alert
        monitor.acknowledge_alert(alert_id, "test_user")
        assert len(monitor.active_alerts) == 0
        assert len(monitor.alert_history) == 1
        
        # Resolve alert
        monitor.resolve_alert(alert_id, "test_user")
        resolved_alert = monitor.alert_history[0]
        assert resolved_alert.status == AlertStatus.RESOLVED


if __name__ == "__main__":
    pytest.main([__file__])
