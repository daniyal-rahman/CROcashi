"""
Unit tests for the Unified Pipeline Orchestrator.

Tests all orchestration, dependency management, and pipeline execution capabilities.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

from src.ncfd.pipeline.unified_orchestrator import UnifiedPipelineOrchestrator
from src.ncfd.pipeline.ctgov_pipeline import CTGovPipeline
from src.ncfd.pipeline.sec_pipeline import SecPipeline


class TestUnifiedPipelineOrchestrator:
    """Test unified pipeline orchestrator functionality."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create a test orchestrator instance."""
        config = {
            'orchestration': {
                'max_concurrent_pipelines': 2,
                'dependency_timeout_minutes': 30,
                'retry_failed_pipelines': True,
                'max_retries': 3
            },
            'pipelines': {
                'ctgov': {
                    'enabled': True,
                    'schedule': 'daily',
                    'priority': 'high'
                },
                'sec': {
                    'enabled': True,
                    'schedule': 'daily',
                    'priority': 'medium'
                }
            },
            'monitoring': {
                'enable_monitoring': True,
                'track_execution_history': True
            }
        }
        return UnifiedPipelineOrchestrator(config)
    
    def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initialization."""
        assert orchestrator.max_concurrent_pipelines == 2
        assert orchestrator.dependency_timeout_minutes == 30
        assert orchestrator.retry_failed_pipelines is True
        assert orchestrator.max_retries == 3
        assert orchestrator.ctgov_enabled is True
        assert orchestrator.sec_enabled is True
        assert orchestrator.monitoring_enabled is True
        assert orchestrator.track_execution_history is True
    
    def test_register_pipeline(self, orchestrator):
        """Test pipeline registration."""
        # Create mock pipelines
        ctgov_pipeline = Mock(spec=CTGovPipeline)
        sec_pipeline = Mock(spec=SecPipeline)
        
        # Register pipelines
        orchestrator.register_pipeline("ctgov", ctgov_pipeline)
        orchestrator.register_pipeline("sec", sec_pipeline)
        
        # Check registration
        assert "ctgov" in orchestrator.pipelines
        assert "sec" in orchestrator.pipelines
        assert orchestrator.pipelines["ctgov"] == ctgov_pipeline
        assert orchestrator.pipelines["sec"] == sec_pipeline
    
    def test_set_pipeline_dependencies(self, orchestrator):
        """Test setting pipeline dependencies."""
        # Set dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        orchestrator.set_pipeline_dependencies("ctgov", [])
        
        # Check dependencies
        assert orchestrator.pipeline_dependencies["sec"] == ["ctgov"]
        assert orchestrator.pipeline_dependencies["ctgov"] == []
    
    def test_check_dependencies_met(self, orchestrator):
        """Test dependency checking."""
        # Set up dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        
        # Mock execution history
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "pipeline_name": "ctgov",
                    "start_time": datetime.utcnow() - timedelta(hours=1),
                    "end_time": datetime.utcnow() - timedelta(minutes=30),
                    "success": True,
                    "status": "completed"
                }
            ]
        }
        
        # Check dependencies
        dependencies_met = orchestrator._check_dependencies_met("sec")
        assert dependencies_met is True
        
        # Check with unmet dependencies
        dependencies_met = orchestrator._check_dependencies_met("ctgov")
        assert dependencies_met is True  # No dependencies
    
    def test_check_dependencies_met_unmet(self, orchestrator):
        """Test dependency checking with unmet dependencies."""
        # Set up dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        
        # No execution history
        orchestrator.execution_history = {}
        
        # Check dependencies
        dependencies_met = orchestrator._check_dependencies_met("sec")
        assert dependencies_met is False
    
    def test_check_dependencies_met_failed(self, orchestrator):
        """Test dependency checking with failed dependencies."""
        # Set up dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        
        # Mock execution history with failed execution
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "pipeline_name": "ctgov",
                    "start_time": datetime.utcnow() - timedelta(hours=1),
                    "end_time": datetime.utcnow() - timedelta(minutes=30),
                    "success": False,
                    "status": "failed"
                }
            ]
        }
        
        # Check dependencies
        dependencies_met = orchestrator._check_dependencies_met("sec")
        assert dependencies_met is False
    
    def test_check_dependencies_met_timeout(self, orchestrator):
        """Test dependency checking with timeout."""
        # Set up dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        
        # Mock execution history with old execution
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "pipeline_name": "ctgov",
                    "start_time": datetime.utcnow() - timedelta(hours=2),
                    "end_time": datetime.utcnow() - timedelta(hours=1, minutes=30),
                    "success": True,
                    "status": "completed"
                }
            ]
        }
        
        # Check dependencies (should timeout)
        dependencies_met = orchestrator._check_dependencies_met("sec")
        assert dependencies_met is False
    
    def test_get_ready_pipelines(self, orchestrator):
        """Test getting ready pipelines."""
        # Set up dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        orchestrator.set_pipeline_dependencies("ctgov", [])
        
        # Mock execution history
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "pipeline_name": "ctgov",
                    "start_time": datetime.utcnow() - timedelta(hours=1),
                    "end_time": datetime.utcnow() - timedelta(minutes=30),
                    "success": True,
                    "status": "completed"
                }
            ]
        }
        
        # Get ready pipelines
        ready_pipelines = orchestrator._get_ready_pipelines()
        
        # CT.gov should be ready (no dependencies)
        assert "ctgov" in ready_pipelines
        # SEC should not be ready (depends on CT.gov)
        assert "sec" not in ready_pipelines
    
    def test_get_ready_pipelines_all_ready(self, orchestrator):
        """Test getting ready pipelines when all are ready."""
        # Set up dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        orchestrator.set_pipeline_dependencies("ctgov", [])
        
        # Mock execution history with recent successful executions
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "pipeline_name": "ctgov",
                    "start_time": datetime.utcnow() - timedelta(minutes=30),
                    "end_time": datetime.utcnow() - timedelta(minutes=15),
                    "success": True,
                    "status": "completed"
                }
            ]
        }
        
        # Get ready pipelines
        ready_pipelines = orchestrator._get_ready_pipelines()
        
        # Both should be ready now
        assert "ctgov" in ready_pipelines
        assert "sec" in ready_pipelines
    
    def test_execute_pipeline(self, orchestrator):
        """Test pipeline execution."""
        # Create mock pipeline
        mock_pipeline = Mock()
        mock_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "test_exec_123",
            "records_processed": 100,
            "execution_time": 30.5
        }
        
        # Register pipeline
        orchestrator.register_pipeline("test_pipeline", mock_pipeline)
        
        # Execute pipeline
        result = orchestrator._execute_pipeline("test_pipeline")
        
        # Check execution
        assert result["success"] is True
        assert result["execution_id"] == "test_exec_123"
        assert result["records_processed"] == 100
        
        # Verify pipeline was called
        mock_pipeline.execute.assert_called_once()
    
    def test_execute_pipeline_failure(self, orchestrator):
        """Test pipeline execution failure."""
        # Create mock pipeline that fails
        mock_pipeline = Mock()
        mock_pipeline.execute.side_effect = Exception("Pipeline execution failed")
        
        # Register pipeline
        orchestrator.register_pipeline("test_pipeline", mock_pipeline)
        
        # Execute pipeline
        result = orchestrator._execute_pipeline("test_pipeline")
        
        # Check failure
        assert result["success"] is False
        assert "error" in result
        assert "Pipeline execution failed" in result["error"]
    
    def test_run_daily_ingestion(self, orchestrator):
        """Test daily ingestion execution."""
        # Create mock pipelines
        ctgov_pipeline = Mock()
        ctgov_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "ctgov_exec_123",
            "records_processed": 50
        }
        
        sec_pipeline = Mock()
        sec_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "sec_exec_123",
            "records_processed": 25
        }
        
        # Register pipelines
        orchestrator.register_pipeline("ctgov", ctgov_pipeline)
        orchestrator.register_pipeline("sec", sec_pipeline)
        
        # Set dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        orchestrator.set_pipeline_dependencies("ctgov", [])
        
        # Run daily ingestion
        results = orchestrator.run_daily_ingestion()
        
        # Check results
        assert len(results) == 2
        assert results["ctgov"]["success"] is True
        assert results["sec"]["success"] is True
        
        # Verify execution order (CT.gov first, then SEC)
        ctgov_call = ctgov_pipeline.execute.call_args_list[0]
        sec_call = sec_pipeline.execute.call_args_list[0]
        assert ctgov_call[1]["execution_id"] == "ctgov_exec_123"
        assert sec_call[1]["execution_id"] == "sec_exec_123"
    
    def test_run_daily_ingestion_with_failure(self, orchestrator):
        """Test daily ingestion with pipeline failure."""
        # Create mock pipelines
        ctgov_pipeline = Mock()
        ctgov_pipeline.execute.return_value = {
            "success": False,
            "execution_id": "ctgov_exec_123",
            "error": "CT.gov pipeline failed"
        }
        
        sec_pipeline = Mock()
        sec_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "sec_exec_123",
            "records_processed": 25
        }
        
        # Register pipelines
        orchestrator.register_pipeline("ctgov", ctgov_pipeline)
        orchestrator.register_pipeline("sec", sec_pipeline)
        
        # Set dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        orchestrator.set_pipeline_dependencies("ctgov", [])
        
        # Run daily ingestion
        results = orchestrator.run_daily_ingestion()
        
        # Check results
        assert results["ctgov"]["success"] is False
        # SEC should not execute due to CT.gov failure
        assert "sec" not in results
        
        # Verify only CT.gov was called
        ctgov_pipeline.execute.assert_called_once()
        sec_pipeline.execute.assert_not_called()
    
    def test_run_backfill(self, orchestrator):
        """Test backfill execution."""
        # Create mock pipelines
        ctgov_pipeline = Mock()
        ctgov_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "ctgov_backfill_123",
            "records_processed": 1000
        }
        
        # Register pipeline
        orchestrator.register_pipeline("ctgov", ctgov_pipeline)
        
        # Run backfill
        results = orchestrator.run_backfill(
            pipeline_name="ctgov",
            start_date="2024-01-01",
            end_date="2024-01-31"
        )
        
        # Check results
        assert results["success"] is True
        assert results["execution_id"] == "ctgov_backfill_123"
        assert results["records_processed"] == 1000
        
        # Verify backfill parameters were passed
        call_args = ctgov_pipeline.execute.call_args
        assert call_args[1]["start_date"] == "2024-01-01"
        assert call_args[1]["end_date"] == "2024-01-31"
    
    def test_run_backfill_invalid_pipeline(self, orchestrator):
        """Test backfill with invalid pipeline."""
        # Run backfill for non-existent pipeline
        with pytest.raises(ValueError, match="Pipeline 'invalid_pipeline' not found"):
            orchestrator.run_backfill(
                pipeline_name="invalid_pipeline",
                start_date="2024-01-01",
                end_date="2024-01-31"
            )
    
    def test_get_execution_status(self, orchestrator):
        """Test getting execution status."""
        # Mock execution history
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "pipeline_name": "ctgov",
                    "start_time": datetime.utcnow() - timedelta(hours=1),
                    "end_time": datetime.utcnow() - timedelta(minutes=30),
                    "success": True,
                    "status": "completed"
                }
            ]
        }
        
        # Get execution status
        status = orchestrator.get_execution_status()
        
        # Check status
        assert "ctgov" in status
        assert status["ctgov"]["last_execution"]["success"] is True
        assert status["ctgov"]["last_execution"]["status"] == "completed"
    
    def test_get_execution_status_no_history(self, orchestrator):
        """Test getting execution status with no history."""
        # No execution history
        orchestrator.execution_history = {}
        
        # Get execution status
        status = orchestrator.get_execution_status()
        
        # Check status
        assert "ctgov" in status
        assert status["ctgov"]["last_execution"] is None
        assert status["ctgov"]["execution_count"] == 0
    
    def test_get_pipeline_health(self, orchestrator):
        """Test getting pipeline health."""
        # Mock execution history with mixed results
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "success": True,
                    "status": "completed"
                },
                {
                    "execution_id": "exec_2",
                    "success": False,
                    "status": "failed"
                },
                {
                    "execution_id": "exec_3",
                    "success": True,
                    "status": "completed"
                }
            ]
        }
        
        # Get pipeline health
        health = orchestrator.get_pipeline_health("ctgov")
        
        # Check health metrics
        assert health["total_executions"] == 3
        assert health["successful_executions"] == 2
        assert health["failed_executions"] == 1
        assert health["success_rate"] == 2/3
        assert health["health_status"] == "degraded"
    
    def test_get_pipeline_health_excellent(self, orchestrator):
        """Test getting pipeline health for excellent pipeline."""
        # Mock execution history with all successful
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "success": True,
                    "status": "completed"
                },
                {
                    "execution_id": "exec_2",
                    "success": True,
                    "status": "completed"
                }
            ]
        }
        
        # Get pipeline health
        health = orchestrator.get_pipeline_health("ctgov")
        
        # Check health metrics
        assert health["total_executions"] == 2
        assert health["successful_executions"] == 2
        assert health["failed_executions"] == 0
        assert health["success_rate"] == 1.0
        assert health["health_status"] == "excellent"
    
    def test_get_pipeline_health_critical(self, orchestrator):
        """Test getting pipeline health for critical pipeline."""
        # Mock execution history with all failed
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "success": False,
                    "status": "failed"
                },
                {
                    "execution_id": "exec_2",
                    "success": False,
                    "status": "failed"
                }
            ]
        }
        
        # Get pipeline health
        health = orchestrator.get_pipeline_health("ctgov")
        
        # Check health metrics
        assert health["total_executions"] == 2
        assert health["successful_executions"] == 0
        assert health["failed_executions"] == 2
        assert health["success_rate"] == 0.0
        assert health["health_status"] == "critical"
    
    def test_export_execution_history(self, orchestrator):
        """Test exporting execution history."""
        # Mock execution history
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "pipeline_name": "ctgov",
                    "start_time": datetime.utcnow() - timedelta(hours=1),
                    "end_time": datetime.utcnow() - timedelta(minutes=30),
                    "success": True,
                    "status": "completed"
                }
            ]
        }
        
        # Export history
        export = orchestrator.export_execution_history("json")
        
        # Parse JSON export
        export_data = json.loads(export)
        
        # Check export
        assert "exported_at" in export_data
        assert "execution_history" in export_data
        assert "ctgov" in export_data["execution_history"]
        assert len(export_data["execution_history"]["ctgov"]) == 1
    
    def test_export_execution_history_invalid_format(self, orchestrator):
        """Test exporting execution history with invalid format."""
        with pytest.raises(ValueError, match="Unsupported export format"):
            orchestrator.export_execution_history("invalid_format")
    
    def test_clear_execution_history(self, orchestrator):
        """Test clearing execution history."""
        # Mock execution history
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_1",
                    "pipeline_name": "ctgov",
                    "success": True
                }
            ],
            "sec": [
                {
                    "execution_id": "exec_2",
                    "pipeline_name": "sec",
                    "success": True
                }
            ]
        }
        
        # Clear history
        orchestrator.clear_execution_history()
        
        # Check that history is cleared
        assert orchestrator.execution_history == {}
    
    def test_clear_execution_history_keep_recent(self, orchestrator):
        """Test clearing execution history keeping recent entries."""
        # Mock execution history with old and new entries
        old_time = datetime.utcnow() - timedelta(days=10)
        recent_time = datetime.utcnow() - timedelta(hours=1)
        
        orchestrator.execution_history = {
            "ctgov": [
                {
                    "execution_id": "exec_old",
                    "pipeline_name": "ctgov",
                    "start_time": old_time,
                    "success": True
                },
                {
                    "execution_id": "exec_recent",
                    "pipeline_name": "ctgov",
                    "start_time": recent_time,
                    "success": True
                }
            ]
        }
        
        # Clear history keeping last 1 entry
        orchestrator.clear_execution_history(keep_last=1)
        
        # Check that only recent entry remains
        assert len(orchestrator.execution_history["ctgov"]) == 1
        assert orchestrator.execution_history["ctgov"][0]["execution_id"] == "exec_recent"


class TestUnifiedPipelineOrchestratorIntegration:
    """Integration tests for the unified pipeline orchestrator."""
    
    @pytest.fixture
    def orchestrator(self):
        """Create a test orchestrator instance."""
        config = {
            'orchestration': {
                'max_concurrent_pipelines': 2,
                'dependency_timeout_minutes': 30,
                'retry_failed_pipelines': True,
                'max_retries': 3
            },
            'pipelines': {
                'ctgov': {
                    'enabled': True,
                    'schedule': 'daily',
                    'priority': 'high'
                },
                'sec': {
                    'enabled': True,
                    'schedule': 'daily',
                    'priority': 'medium'
                }
            },
            'monitoring': {
                'enable_monitoring': True,
                'track_execution_history': True
            }
        }
        return UnifiedPipelineOrchestrator(config)
    
    def test_end_to_end_orchestration_workflow(self, orchestrator):
        """Test complete end-to-end orchestration workflow."""
        # Create mock pipelines
        ctgov_pipeline = Mock()
        ctgov_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "ctgov_exec_123",
            "records_processed": 100,
            "execution_time": 45.2
        }
        
        sec_pipeline = Mock()
        sec_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "sec_exec_123",
            "records_processed": 50,
            "execution_time": 30.1
        }
        
        # Register pipelines
        orchestrator.register_pipeline("ctgov", ctgov_pipeline)
        orchestrator.register_pipeline("sec", sec_pipeline)
        
        # Set dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        orchestrator.set_pipeline_dependencies("ctgov", [])
        
        # Run daily ingestion
        results = orchestrator.run_daily_ingestion()
        
        # Check results
        assert len(results) == 2
        assert results["ctgov"]["success"] is True
        assert results["sec"]["success"] is True
        
        # Check execution history
        assert "ctgov" in orchestrator.execution_history
        assert "sec" in orchestrator.execution_history
        
        # Check execution order
        ctgov_history = orchestrator.execution_history["ctgov"]
        sec_history = orchestrator.execution_history["sec"]
        
        assert len(ctgov_history) == 1
        assert len(sec_history) == 1
        assert ctgov_history[0]["execution_id"] == "ctgov_exec_123"
        assert sec_history[0]["execution_id"] == "sec_exec_123"
        
        # Verify dependency order (CT.gov should execute before SEC)
        ctgov_start = ctgov_history[0]["start_time"]
        sec_start = sec_history[0]["start_time"]
        assert ctgov_start <= sec_start
    
    def test_pipeline_failure_handling(self, orchestrator):
        """Test handling of pipeline failures."""
        # Create mock pipelines
        ctgov_pipeline = Mock()
        ctgov_pipeline.execute.return_value = {
            "success": False,
            "execution_id": "ctgov_exec_123",
            "error": "CT.gov API rate limit exceeded"
        }
        
        sec_pipeline = Mock()
        sec_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "sec_exec_123",
            "records_processed": 50
        }
        
        # Register pipelines
        orchestrator.register_pipeline("ctgov", ctgov_pipeline)
        orchestrator.register_pipeline("sec", sec_pipeline)
        
        # Set dependencies
        orchestrator.set_pipeline_dependencies("sec", ["ctgov"])
        orchestrator.set_pipeline_dependencies("ctgov", [])
        
        # Run daily ingestion
        results = orchestrator.run_daily_ingestion()
        
        # Check results
        assert results["ctgov"]["success"] is False
        assert "sec" not in results  # SEC should not execute
        
        # Check execution history
        assert "ctgov" in orchestrator.execution_history
        assert "sec" not in orchestrator.execution_history
        
        # Check failure details
        ctgov_history = orchestrator.execution_history["ctgov"]
        assert len(ctgov_history) == 1
        assert ctgov_history[0]["success"] is False
        assert "CT.gov API rate limit exceeded" in ctgov_history[0]["error"]
    
    def test_concurrent_pipeline_execution(self, orchestrator):
        """Test concurrent pipeline execution."""
        # Set max concurrent to 1 to force sequential execution
        orchestrator.max_concurrent_pipelines = 1
        
        # Create mock pipelines
        ctgov_pipeline = Mock()
        ctgov_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "ctgov_exec_123",
            "records_processed": 100
        }
        
        sec_pipeline = Mock()
        sec_pipeline.execute.return_value = {
            "success": True,
            "execution_id": "sec_exec_123",
            "records_processed": 50
        }
        
        # Register pipelines
        orchestrator.register_pipeline("ctgov", ctgov_pipeline)
        orchestrator.register_pipeline("sec", sec_pipeline)
        
        # Set no dependencies (both can run independently)
        orchestrator.set_pipeline_dependencies("sec", [])
        orchestrator.set_pipeline_dependencies("ctgov", [])
        
        # Run daily ingestion
        results = orchestrator.run_daily_ingestion()
        
        # Check results
        assert len(results) == 2
        assert results["ctgov"]["success"] is True
        assert results["sec"]["success"] is True
        
        # With max_concurrent=1, pipelines should execute sequentially
        # Verify execution order (should be based on registration order or priority)
        assert "ctgov" in orchestrator.execution_history
        assert "sec" in orchestrator.execution_history


if __name__ == "__main__":
    pytest.main([__file__])
