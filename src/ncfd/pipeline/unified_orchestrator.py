"""
Unified Pipeline Orchestrator for CT.gov and SEC filing ingestion.

This module provides:
- Coordinated execution of CT.gov and SEC pipelines
- Dependency management and workflow coordination
- Unified monitoring and reporting
- Integration with existing systems
- Error handling and recovery
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import json
from dataclasses import dataclass, field

from .orchestrator import PipelineOrchestrator
from .ctgov_pipeline import CtgovPipeline
from .sec_pipeline import SecPipeline

logger = logging.getLogger(__name__)


@dataclass
class PipelineExecutionResult:
    """Result of a pipeline execution."""
    pipeline_name: str
    success: bool
    start_time: datetime
    end_time: datetime
    processing_time_seconds: float
    
    # Pipeline-specific metrics
    trials_processed: int = 0
    trials_updated: int = 0
    trials_new: int = 0
    changes_detected: int = 0
    significant_changes: int = 0
    
    filings_processed: int = 0
    filings_successful: int = 0
    filings_failed: int = 0
    new_filings: int = 0
    updated_filings: int = 0
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Calculate processing time."""
        self.processing_time_seconds = (self.end_time - self.start_time).total_seconds()


@dataclass
class OrchestrationResult:
    """Result of orchestrated pipeline execution."""
    execution_id: str
    start_time: datetime
    end_time: datetime
    total_processing_time: float
    
    # Pipeline results
    ctgov_result: Optional[PipelineExecutionResult] = None
    sec_result: Optional[PipelineExecutionResult] = None
    
    # Overall metrics
    total_trials_processed: int = 0
    total_filings_processed: int = 0
    total_changes_detected: int = 0
    total_significant_changes: int = 0
    
    # Success tracking
    all_pipelines_successful: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Calculate overall metrics."""
        self.total_processing_time = (self.end_time - self.start_time).total_seconds()
        
        # Aggregate metrics from pipeline results
        if self.ctgov_result:
            self.total_trials_processed += self.ctgov_result.trials_processed
            self.total_changes_detected += self.ctgov_result.changes_detected
            self.total_significant_changes += self.ctgov_result.significant_changes
        
        if self.sec_result:
            self.total_filings_processed += self.sec_result.filings_processed
        
        # Determine overall success
        self.all_pipelines_successful = (
            self.ctgov_result.success if self.ctgov_result else True and
            self.sec_result.success if self.sec_result else True
        )


class UnifiedPipelineOrchestrator:
    """
    Unified orchestrator for CT.gov and SEC filing pipelines.
    
    Features:
    - Coordinated pipeline execution
    - Dependency management
    - Unified monitoring and reporting
    - Error handling and recovery
    - Integration coordination
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the unified orchestrator.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize pipelines
        self.ctgov_pipeline = CtgovPipeline(config.get('ctgov', {}))
        self.sec_pipeline = SecPipeline(config.get('sec', {}))
        
        # Orchestration state
        self.state_file = Path(config.get('state_file', '.state/unified_orchestrator.json'))
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.orchestration_state = self._load_orchestration_state()
        
        # Execution tracking
        self.execution_history: List[OrchestrationResult] = []
        self.current_execution: Optional[OrchestrationResult] = None
        
        # Configuration
        self.execution_order = config.get('execution_order', ['ctgov', 'sec'])
        self.parallel_execution = config.get('parallel_execution', False)
        self.dependency_checking = config.get('dependency_checking', True)
        
        # Error handling
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay_seconds = config.get('retry_delay_seconds', 300)  # 5 minutes
        
        self.logger.info("Unified Pipeline Orchestrator initialized")
    
    def run_daily_ingestion(self, force_full_scan: bool = False) -> OrchestrationResult:
        """
        Run daily ingestion for all pipelines.
        
        Args:
            force_full_scan: Force full scan for all pipelines
            
        Returns:
            Orchestration result
        """
        execution_id = f"daily_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        start_time = datetime.utcnow()
        
        self.logger.info(f"Starting daily ingestion: {execution_id}")
        
        # Create execution result
        self.current_execution = OrchestrationResult(
            execution_id=execution_id,
            start_time=start_time,
            end_time=start_time  # Will be updated
        )
        
        try:
            # Execute pipelines based on configuration
            if self.parallel_execution:
                result = self._run_parallel_execution(force_full_scan)
            else:
                result = self._run_sequential_execution(force_full_scan)
            
            # Update execution result
            self.current_execution.end_time = datetime.utcnow()
            self.current_execution.ctgov_result = result.get('ctgov')
            self.current_execution.sec_result = result.get('sec')
            
            # Store in history
            self.execution_history.append(self.current_execution)
            
            # Update orchestration state
            self._update_orchestration_state()
            
            self.logger.info(
                f"Daily ingestion completed: {self.current_execution.total_trials_processed} trials, "
                f"{self.current_execution.total_filings_processed} filings in "
                f"{self.current_execution.total_processing_time:.1f}s"
            )
            
            return self.current_execution
            
        except Exception as e:
            error_msg = f"Error in daily ingestion: {e}"
            self.logger.error(error_msg)
            self.current_execution.errors.append(error_msg)
            self.current_execution.end_time = datetime.utcnow()
            return self.current_execution
    
    def _run_sequential_execution(self, force_full_scan: bool) -> Dict[str, Optional[PipelineExecutionResult]]:
        """Run pipelines sequentially."""
        results = {}
        
        for pipeline_name in self.execution_order:
            try:
                if pipeline_name == 'ctgov':
                    results['ctgov'] = self._execute_ctgov_pipeline(force_full_scan)
                elif pipeline_name == 'sec':
                    # Check dependencies if enabled
                    if self.dependency_checking and not self._check_ctgov_dependencies():
                        self.logger.warning("CT.gov dependencies not met, skipping SEC pipeline")
                        results['sec'] = None
                        continue
                    
                    results['sec'] = self._execute_sec_pipeline(force_full_scan)
                
                # Wait between pipelines
                time.sleep(1)
                
            except Exception as e:
                error_msg = f"Error executing {pipeline_name} pipeline: {e}"
                self.logger.error(error_msg)
                results[pipeline_name] = None
        
        return results
    
    def _run_parallel_execution(self, force_full_scan: bool) -> Dict[str, Optional[PipelineExecutionResult]]:
        """Run pipelines in parallel (if supported)."""
        # For now, fall back to sequential execution
        # TODO: Implement true parallel execution with threading
        self.logger.warning("Parallel execution not yet implemented, using sequential")
        return self._run_sequential_execution(force_full_scan)
    
    def _execute_ctgov_pipeline(self, force_full_scan: bool) -> Optional[PipelineExecutionResult]:
        """Execute CT.gov pipeline."""
        start_time = datetime.utcnow()
        self.logger.info("Executing CT.gov pipeline")
        
        try:
            # Execute pipeline
            result = self.ctgov_pipeline.run_daily_ingestion(force_full_scan)
            
            # Create execution result
            execution_result = PipelineExecutionResult(
                pipeline_name="ctgov",
                success=result.success,
                start_time=start_time,
                end_time=datetime.utcnow(),
                trials_processed=result.trials_processed,
                trials_updated=result.trials_updated,
                trials_new=result.trials_new,
                changes_detected=result.changes_detected,
                significant_changes=result.significant_changes,
                errors=result.errors,
                warnings=result.warnings
            )
            
            self.logger.info(f"CT.gov pipeline completed: {result.trials_processed} trials processed")
            return execution_result
            
        except Exception as e:
            error_msg = f"Error executing CT.gov pipeline: {e}"
            self.logger.error(error_msg)
            
            # Create error result
            execution_result = PipelineExecutionResult(
                pipeline_name="ctgov",
                success=False,
                start_time=start_time,
                end_time=datetime.utcnow(),
                errors=[error_msg]
            )
            
            return execution_result
    
    def _execute_sec_pipeline(self, force_full_scan: bool) -> Optional[PipelineExecutionResult]:
        """Execute SEC pipeline."""
        start_time = datetime.utcnow()
        self.logger.info("Executing SEC pipeline")
        
        try:
            # Execute pipeline
            result = self.sec_pipeline.run_daily_scan(force_full_scan)
            
            # Create execution result
            execution_result = PipelineExecutionResult(
                pipeline_name="sec",
                success=result.success,
                start_time=start_time,
                end_time=datetime.utcnow(),
                filings_processed=result.filings_processed,
                filings_successful=result.filings_successful,
                filings_failed=result.filings_failed,
                new_filings=result.new_filings,
                updated_filings=result.updated_filings,
                errors=result.errors,
                warnings=result.warnings
            )
            
            self.logger.info(f"SEC pipeline completed: {result.filings_processed} filings processed")
            return execution_result
            
        except Exception as e:
            error_msg = f"Error executing SEC pipeline: {e}"
            self.logger.error(error_msg)
            
            # Create error result
            execution_result = PipelineExecutionResult(
                pipeline_name="sec",
                success=False,
                start_time=start_time,
                end_time=datetime.utcnow(),
                errors=[error_msg]
            )
            
            return execution_result
    
    def _check_ctgov_dependencies(self) -> bool:
        """Check if CT.gov dependencies are met for SEC pipeline."""
        try:
            # Check if CT.gov pipeline has run recently
            last_ctgov_run = self.orchestration_state.get('last_ctgov_run')
            if not last_ctgov_run:
                return False
            
            last_run_time = datetime.fromisoformat(last_ctgov_run)
            time_since_run = datetime.utcnow() - last_run_time
            
            # Require CT.gov to have run within the last 24 hours
            return time_since_run < timedelta(hours=24)
            
        except Exception as e:
            self.logger.warning(f"Error checking CT.gov dependencies: {e}")
            return False
    
    def run_backfill(
        self, 
        start_date: datetime, 
        end_date: datetime,
        pipelines: Optional[List[str]] = None
    ) -> OrchestrationResult:
        """
        Run backfill for specified pipelines.
        
        Args:
            start_date: Start date for backfill
            end_date: End date for backfill
            pipelines: Pipelines to backfill (None for all)
            
        Returns:
            Orchestration result
        """
        execution_id = f"backfill_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
        start_time = datetime.utcnow()
        
        self.logger.info(f"Starting backfill: {execution_id}")
        
        # Create execution result
        self.current_execution = OrchestrationResult(
            execution_id=execution_id,
            start_time=start_time,
            end_time=start_time
        )
        
        try:
            # Determine which pipelines to run
            pipelines_to_run = pipelines or ['ctgov', 'sec']
            results = {}
            
            for pipeline_name in pipelines_to_run:
                if pipeline_name == 'ctgov':
                    results['ctgov'] = self._execute_ctgov_backfill(start_date, end_date)
                elif pipeline_name == 'sec':
                    results['sec'] = self._execute_sec_backfill(start_date, end_date)
            
            # Update execution result
            self.current_execution.end_time = datetime.utcnow()
            self.current_execution.ctgov_result = results.get('ctgov')
            self.current_execution.sec_result = results.get('sec')
            
            # Store in history
            self.execution_history.append(self.current_execution)
            
            # Update orchestration state
            self._update_orchestration_state()
            
            self.logger.info(f"Backfill completed: {execution_id}")
            return self.current_execution
            
        except Exception as e:
            error_msg = f"Error in backfill: {e}"
            self.logger.error(error_msg)
            self.current_execution.errors.append(error_msg)
            self.current_execution.end_time = datetime.utcnow()
            return self.current_execution
    
    def _execute_ctgov_backfill(self, start_date: datetime, end_date: datetime) -> Optional[PipelineExecutionResult]:
        """Execute CT.gov backfill."""
        start_time = datetime.utcnow()
        self.logger.info("Executing CT.gov backfill")
        
        try:
            # TODO: Implement CT.gov backfill
            # result = self.ctgov_pipeline.run_backfill(start_date, end_date)
            
            # For now, return None
            return None
            
        except Exception as e:
            self.logger.error(f"Error executing CT.gov backfill: {e}")
            return None
    
    def _execute_sec_backfill(self, start_date: datetime, end_date: datetime) -> Optional[PipelineExecutionResult]:
        """Execute SEC backfill."""
        start_time = datetime.utcnow()
        self.logger.info("Executing SEC backfill")
        
        try:
            # Execute backfill
            result = self.sec_pipeline.run_backfill(start_date.date(), end_date.date())
            
            # Create execution result
            execution_result = PipelineExecutionResult(
                pipeline_name="sec",
                success=result.success,
                start_time=start_time,
                end_time=datetime.utcnow(),
                filings_processed=result.filings_processed,
                filings_successful=result.filings_successful,
                filings_failed=result.filings_failed,
                new_filings=result.new_filings,
                updated_filings=result.updated_filings,
                errors=result.errors,
                warnings=result.warnings
            )
            
            return execution_result
            
        except Exception as e:
            self.logger.error(f"Error executing SEC backfill: {e}")
            return None
    
    def get_orchestration_status(self) -> Dict[str, Any]:
        """Get current orchestration status."""
        return {
            'current_execution': self.current_execution.execution_id if self.current_execution else None,
            'execution_history_count': len(self.execution_history),
            'last_successful_run': self._get_last_successful_run(),
            'pipeline_status': {
                'ctgov': self._get_pipeline_status('ctgov'),
                'sec': self._get_pipeline_status('sec')
            },
            'configuration': {
                'execution_order': self.execution_order,
                'parallel_execution': self.parallel_execution,
                'dependency_checking': self.dependency_checking
            }
        }
    
    def _get_last_successful_run(self) -> Optional[str]:
        """Get the last successful orchestration run."""
        for result in reversed(self.execution_history):
            if result.all_pipelines_successful:
                return result.execution_id
        return None
    
    def _get_pipeline_status(self, pipeline_name: str) -> Dict[str, Any]:
        """Get status for a specific pipeline."""
        if pipeline_name == 'ctgov':
            return self.ctgov_pipeline.get_pipeline_status()
        elif pipeline_name == 'sec':
            return self.sec_pipeline.get_pipeline_status()
        else:
            return {'error': f'Unknown pipeline: {pipeline_name}'}
    
    def _load_orchestration_state(self) -> Dict[str, Any]:
        """Load orchestration state from file."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load orchestration state: {e}")
        
        return {}
    
    def _update_orchestration_state(self):
        """Update orchestration state with latest results."""
        try:
            if self.current_execution:
                # Update last run times
                if self.current_execution.ctgov_result:
                    self.orchestration_state['last_ctgov_run'] = self.current_execution.end_time.isoformat()
                
                if self.current_execution.sec_result:
                    self.orchestration_state['last_sec_run'] = self.current_execution.end_time.isoformat()
                
                # Update last orchestration run
                self.orchestration_state['last_orchestration_run'] = self.current_execution.end_time.isoformat()
                self.orchestration_state['last_execution_id'] = self.current_execution.execution_id
            
            # Save state
            with open(self.state_file, 'w') as f:
                json.dump(self.orchestration_state, f, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"Failed to update orchestration state: {e}")
    
    def get_execution_history(self, limit: Optional[int] = None) -> List[OrchestrationResult]:
        """Get execution history, optionally limited."""
        if limit:
            return self.execution_history[-limit:]
        return self.execution_history
    
    def clear_execution_history(self, keep_last: int = 10):
        """Clear execution history, keeping the last N executions."""
        if len(self.execution_history) > keep_last:
            self.execution_history = self.execution_history[-keep_last:]
            self.logger.info(f"Cleared execution history, keeping last {keep_last} executions")
    
    def export_execution_report(self, execution_id: str, format: str = "json") -> Optional[str]:
        """Export execution report in specified format."""
        # Find execution
        execution = None
        for result in self.execution_history:
            if result.execution_id == execution_id:
                execution = result
                break
        
        if not execution:
            return None
        
        if format == "json":
            import json
            return json.dumps(vars(execution), indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")
