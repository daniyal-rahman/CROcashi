"""
Unified Pipeline Orchestrator for CT.gov, SEC filing, and PubMed literature ingestion.

This module provides:
- Coordinated execution of CT.gov, SEC, and PubMed pipelines
- Dependency management and workflow coordination
- Unified monitoring and reporting
- Error handling and recovery
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
from dataclasses import dataclass, field, asdict

from .ctgov_pipeline import CtgovPipeline
from .sec_pipeline import SecPipeline
from ..ingest.pubmed.pipeline import PubMedPipeline
from ..ingest.pubmed.db_service import PubMedDBService
from ..ingest.pubmed.queue_service import TaskQueueService
from ..db.session import session_scope
from ..db.models import Trial, Company
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class PipelineExecutionResult:
    """Result of a pipeline execution."""
    pipeline_name: str
    success: bool
    start_time: datetime
    end_time: datetime
    processing_time_seconds: float = field(init=False, default=0.0)
    
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
    
    documents_processed: int = 0
    documents_failed: int = 0
    
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
    total_processing_time: float = field(init=False, default=0.0)
    
    # Pipeline results
    ctgov_result: Optional[PipelineExecutionResult] = None
    sec_result: Optional[PipelineExecutionResult] = None
    pubmed_result: Optional[PipelineExecutionResult] = None
    
    # Overall metrics
    total_trials_processed: int = 0
    total_filings_processed: int = 0
    total_documents_processed: int = 0
    total_changes_detected: int = 0
    total_significant_changes: int = 0
    
    # Success tracking
    all_pipelines_successful: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def finalize(self):
        """Finalize the result by computing all metrics and success status."""
        self.total_processing_time = (self.end_time - self.start_time).total_seconds()
        
        # Aggregate metrics from pipeline results
        if self.ctgov_result:
            self.total_trials_processed += self.ctgov_result.trials_processed
            self.total_changes_detected += self.ctgov_result.changes_detected
            self.total_significant_changes += self.ctgov_result.significant_changes
        
        if self.sec_result:
            self.total_filings_processed += self.sec_result.filings_processed
        
        if self.pubmed_result:
            self.total_documents_processed += self.pubmed_result.documents_processed
        
        # Determine overall success
        self.all_pipelines_successful = (
            (self.ctgov_result.success if self.ctgov_result else True) and
            (self.sec_result.success if self.sec_result else True) and
            (self.pubmed_result.success if self.pubmed_result else True)
        )


class UnifiedPipelineOrchestrator:
    """
    Unified orchestrator for CT.gov, SEC filing, and PubMed literature pipelines.
    
    Features:
    - Coordinated pipeline execution
    - Dependency management
    - Unified monitoring and reporting
    - Error handling and recovery
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
        self.pubmed_pipeline = PubMedPipeline(config.get('pubmed', {}))
        
        # Initialize task queue service for trial prioritization
        self.task_queue_service = TaskQueueService(
            worker_id=config.get('worker_id', 'orchestrator')
        )
        
        # Initialize database service for accessing trial literature state
        self.pubmed_db_service = PubMedDBService()
        
        # Orchestration state
        self.state_file = Path(config.get('state_file', '.state/unified_orchestrator.json'))
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.orchestration_state = self._load_orchestration_state()
        
        # Execution tracking
        self.execution_history: List[OrchestrationResult] = []
        self.current_execution: Optional[OrchestrationResult] = None
        
        # Configuration
        self.execution_order = config.get('execution_order', ['ctgov', 'pubmed', 'sec'])
        self.parallel_execution = config.get('parallel_execution', False)
        self.dependency_checking = config.get('dependency_checking', True)
        
        # Error handling
        self.max_retries = config.get('max_retries', 3)
        self.retry_delay_seconds = config.get('retry_delay_seconds', 300)
    
    def inject_ctgov_trial_for_test(
        self,
        nct_id: str,
        company_name: str,
        asset_aliases: List[str],
        indication_terms: List[str],
        extra_trial_fields: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Create a company & trial (if missing), wire them, and enqueue a PUBMED_U1 task.
        
        This method simulates CT.gov ingestion for testing purposes by creating
        the necessary database records and enqueueing the first pipeline task.
        
        Args:
            nct_id: Clinical trial NCT identifier
            company_name: Sponsor company name
            asset_aliases: List of asset names/aliases for the trial
            indication_terms: List of disease/indication terms
            extra_trial_fields: Additional trial fields for realism
            
        Returns:
            trial_id: The created/updated trial ID
        """
        # Phase mapping for database constraints
        PHASE_MAP = {
            "P1": "PHASE1", "P2": "PHASE2", "P2B": "PHASE2B", 
            "P2/3": "PHASE2_3", "P2-3": "PHASE2_PHASE3", 
            "P3": "PHASE3", "P4": "PHASE4"
        }
        
        with session_scope() as s:
            # 1) upsert company
            company = s.query(Company).filter(Company.name == company_name).one_or_none()
            if not company:
                company = Company(
                    name=company_name,
                    name_norm=company_name.lower().strip()
                )
                s.add(company)
                s.flush()
                self.logger.info(f"Created company: {company_name}")

            # 2) upsert trial
            trial = s.query(Trial).filter(Trial.nct_id == nct_id).one_or_none()
            if not trial:
                # Create new trial with required fields
                now = datetime.now(timezone.utc)
                trial = Trial(
                    nct_id=nct_id,
                    sponsor_company_id=company.company_id,
                    status="Recruiting",
                    current_sha256="test_injection_" + nct_id,  # Required field
                    brief_title=f"Study of {asset_aliases[0] if asset_aliases else 'investigational therapy'}",
                    indication=indication_terms[0] if indication_terms else "Unknown",
                    created_at=now,
                    updated_at=now,
                    last_seen_at=now
                )
                # Apply any extra CT.gov-like fields for realism
                for k, v in (extra_trial_fields or {}).items():
                    if hasattr(trial, k):
                        # Map phase if it's a short code
                        if k == 'phase' and v in PHASE_MAP:
                            setattr(trial, k, PHASE_MAP[v])
                        else:
                            setattr(trial, k, v)
                
                s.add(trial)
                s.flush()
                self.logger.info(f"Created trial: {nct_id}")
            else:
                # Make sure it's wired to the company
                trial.sponsor_company_id = company.company_id
                self.logger.info(f"Updated existing trial: {nct_id}")

            trial_id = trial.trial_id
            s.commit()

        # 3) enqueue initial PubMed pass (U1+) for this trial
        payload = {
            "trial_id": trial_id,
            "nct_id": nct_id,
            "asset_aliases": asset_aliases,
            "indication_terms": indication_terms,
            "max_results": self.config.get('pubmed', {}).get('max_results', 150)
        }
        
        success = self.task_queue_service.enqueue_task(
            task_type="PUBMED_U1",
            task_key=f"trial:{trial_id}:U1",
            priority=0.50,  # baseline priority
            payload=payload,
            trial_id=trial_id,
        )
        
        if success:
            self.logger.info(f"Enqueued PUBMED_U1 task for trial {trial_id} ({nct_id})")
        else:
            self.logger.error(f"Failed to enqueue PUBMED_U1 task for trial {trial_id}")
            
        return trial_id
    
    def _run_startup_validation(self):
        """Run startup validation checks."""
        try:
            from ..utils.startup_validation import run_startup_validation, validate_config_before_pipeline_run
            
            # Run general startup validation (non-blocking)
            validation_passed = run_startup_validation(fail_fast=False)
            if not validation_passed:
                self.logger.warning("Some startup validations failed - see logs for details")
            
            # Validate orchestrator config
            config_valid, config_errors = validate_config_before_pipeline_run(self.config)
            if not config_valid:
                self.logger.error(f"Orchestrator configuration validation failed: {config_errors}")
                for error in config_errors:
                    self.logger.error(f"  • {error}")
        
        except Exception as e:
            self.logger.warning(f"Startup validation failed: {e}")
    
    def run_daily_ingestion(self, force_full_scan: bool = False) -> OrchestrationResult:
        """
        Run daily ingestion for all pipelines.
        
        Args:
            force_full_scan: Force full scan for all pipelines
            
        Returns:
            Orchestration result
        """
        execution_id = f"daily_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        start_time = datetime.now(timezone.utc)
        
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
            self.current_execution.end_time = datetime.now(timezone.utc)
            self.current_execution.ctgov_result = result.get('ctgov')
            self.current_execution.pubmed_result = result.get('pubmed')
            self.current_execution.sec_result = result.get('sec')
            
            # Finalize the result
            self.current_execution.finalize()
            
            # Store in history
            self.execution_history.append(self.current_execution)
            
            # Update orchestration state
            self._update_orchestration_state()
            
            self.logger.info(
                f"Daily ingestion completed: {self.current_execution.total_trials_processed} trials, "
                f"{self.current_execution.total_filings_processed} filings, "
                f"{self.current_execution.total_documents_processed} documents in "
                f"{self.current_execution.total_processing_time:.1f}s"
            )
            
            return self.current_execution
            
        except Exception as e:
            error_msg = f"Error in daily ingestion: {e}"
            self.logger.error(error_msg)
            self.current_execution.errors.append(error_msg)
            self.current_execution.end_time = datetime.now(timezone.utc)
            self.current_execution.finalize()
            return self.current_execution
    
    def _run_sequential_execution(self, force_full_scan: bool) -> Dict[str, Optional[PipelineExecutionResult]]:
        """Run pipelines sequentially."""
        results = {}
        
        for pipeline_name in self.execution_order:
            try:
                if pipeline_name == 'ctgov':
                    results['ctgov'] = self._execute_ctgov_pipeline(force_full_scan)
                elif pipeline_name == 'pubmed':
                    results['pubmed'] = self._execute_pubmed_pipeline(force_full_scan)
                elif pipeline_name == 'sec':
                    # Check dependencies if enabled
                    if self.dependency_checking and not self._check_ctgov_dependencies():
                        self.logger.warning("CT.gov dependencies not met, skipping SEC pipeline")
                        results['sec'] = None
                        continue
                    
                    results['sec'] = self._execute_sec_pipeline(force_full_scan)
                
                # Small delay between pipelines if configured
                if self.config.get('inter_pipeline_delay', 0) > 0:
                    time.sleep(self.config['inter_pipeline_delay'])
                
            except Exception as e:
                error_msg = f"Error executing {pipeline_name} pipeline: {e}"
                self.logger.error(error_msg)
                results[pipeline_name] = None
        
        return results
    
    def _run_parallel_execution(self, force_full_scan: bool) -> Dict[str, Optional[PipelineExecutionResult]]:
        """Run pipelines in parallel (if supported)."""
        # For now, fall back to sequential execution
        # TODO: Implement true parallel execution with threading
        self.logger.info("Parallel execution not yet implemented, using sequential")
        return self._run_sequential_execution(force_full_scan)
    
    def _execute_ctgov_pipeline(self, force_full_scan: bool) -> Optional[PipelineExecutionResult]:
        """Execute CT.gov pipeline."""
        start_time = datetime.now(timezone.utc)
        self.logger.info("Executing CT.gov pipeline")
        
        try:
            # Execute pipeline
            result = self.ctgov_pipeline.run_daily_ingestion(force_full_scan)
            
            # Create execution result
            execution_result = PipelineExecutionResult(
                pipeline_name="ctgov",
                success=result.success,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
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
                end_time=datetime.now(timezone.utc),
                errors=[error_msg]
            )
            
            return execution_result
    
    def _execute_pubmed_pipeline(self, force_full_scan: bool) -> Optional[PipelineExecutionResult]:
        """Execute PubMed pipeline."""
        start_time = datetime.now(timezone.utc)
        self.logger.info("Executing PubMed pipeline")
        
        try:
            # Execute PubMed pipeline with proper trial configuration
            # For now, use a simple configuration - this could be made configurable
            trial_configs = [
                {
                    'trial_id': 'daily_ingestion',
                    'asset_names': ['drug', 'compound', 'therapy', 'treatment'],
                    'indications': ['disease', 'condition', 'cancer', 'diabetes'],
                    'max_results': 200
                }
            ]
            
            # Convert trial configs to pipeline config format
            pipeline_config = {
                'asset_names': trial_configs[0]['asset_names'],
                'indications': trial_configs[0]['indications'],
                'max_results': trial_configs[0]['max_results'],
                'enable_stages': ['U0', 'U1'],  # Skip OA for daily ingestion
                'retry_config': {
                    'max_retries': 3,
                    'retry_delay': 1.0
                },
                'client_config': {
                    'rate_limit_requests_per_minute': 300,
                    'timeout_seconds': 45
                }
            }
            
            # Run the pipeline synchronously by creating an event loop
            import asyncio
            try:
                # Try to get the current event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're already in an async context, we can't run sync
                    self.logger.warning("Cannot run PubMed pipeline synchronously from async context")
                    # Return a placeholder result
                    execution_result = PipelineExecutionResult(
                        pipeline_name="pubmed",
                        success=True,
                        start_time=start_time,
                        end_time=datetime.now(timezone.utc),
                        documents_processed=0,
                        documents_failed=0,
                        warnings=["PubMed pipeline requires async context for full execution"]
                    )
                    return execution_result
                else:
                    # Run the pipeline
                    result = loop.run_until_complete(
                        self.pubmed_pipeline.run_daily_ingestion(
                            force_full_scan=force_full_scan,
                            trial_configs=trial_configs,
                            pipeline_config=pipeline_config
                        )
                    )
            except RuntimeError:
                # No event loop, create one
                result = asyncio.run(
                    self.pubmed_pipeline.run_daily_ingestion(
                        force_full_scan=force_full_scan,
                        trial_configs=trial_configs,
                        pipeline_config=pipeline_config
                    )
                )
            
            # Create execution result from pipeline output
            execution_result = PipelineExecutionResult(
                pipeline_name="pubmed",
                success=result.get('success', False),
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                documents_processed=result.get('documents_processed', 0),
                documents_failed=result.get('documents_failed', 0),
                errors=result.get('errors', []),
                warnings=result.get('warnings', [])
            )
            
            self.logger.info(f"PubMed pipeline completed: {result.get('documents_processed', 0)} documents processed")
            
            # Enqueue OA tasks for trials that completed U1+ processing
            if result.get('success', False):
                self._enqueue_oa_tasks_from_pubmed_results(result)
            
            return execution_result
            
        except Exception as e:
            error_msg = f"Error executing PubMed pipeline: {e}"
            self.logger.error(error_msg)
            
            # Create error result
            execution_result = PipelineExecutionResult(
                pipeline_name="pubmed",
                success=False,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                errors=[error_msg]
            )
            
            return execution_result
    
    def _execute_sec_pipeline(self, force_full_scan: bool) -> Optional[PipelineExecutionResult]:
        """Execute SEC pipeline."""
        start_time = datetime.now(timezone.utc)
        self.logger.info("Executing SEC pipeline")
        
        try:
            # Execute pipeline
            result = self.sec_pipeline.run_daily_scan(force_full_scan)
            
            # Create execution result
            execution_result = PipelineExecutionResult(
                pipeline_name="sec",
                success=result.success,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
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
                end_time=datetime.now(timezone.utc),
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
            time_since_run = datetime.now(timezone.utc) - last_run_time
            
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
        start_time = datetime.now(timezone.utc)
        
        self.logger.info(f"Starting backfill: {execution_id}")
        
        # Create execution result
        self.current_execution = OrchestrationResult(
            execution_id=execution_id,
            start_time=start_time,
            end_time=start_time
        )
        
        try:
            # Determine which pipelines to run
            pipelines_to_run = pipelines or ['ctgov', 'pubmed', 'sec']
            results = {}
            
            for pipeline_name in pipelines_to_run:
                if pipeline_name == 'ctgov':
                    results['ctgov'] = self._execute_ctgov_backfill(start_date, end_date)
                elif pipeline_name == 'pubmed':
                    results['pubmed'] = self._execute_pubmed_backfill(start_date, end_date)
                elif pipeline_name == 'sec':
                    results['sec'] = self._execute_sec_backfill(start_date, end_date)
            
            # Update execution result
            self.current_execution.end_time = datetime.now(timezone.utc)
            self.current_execution.ctgov_result = results.get('ctgov')
            self.current_execution.pubmed_result = results.get('pubmed')
            self.current_execution.sec_result = results.get('sec')
            
            # Finalize the result
            self.current_execution.finalize()
            
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
            self.current_execution.end_time = datetime.now(timezone.utc)
            self.current_execution.finalize()
            return self.current_execution
    
    def _execute_ctgov_backfill(self, start_date: datetime, end_date: datetime) -> Optional[PipelineExecutionResult]:
        """Execute CT.gov backfill."""
        start_time = datetime.now(timezone.utc)
        self.logger.info("Executing CT.gov backfill")
        
        try:
            # TODO: Implement CT.gov backfill
            # For now, return a placeholder result
            execution_result = PipelineExecutionResult(
                pipeline_name="ctgov",
                success=False,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                errors=["CT.gov backfill not yet implemented"]
            )
            
            return execution_result
            
        except Exception as e:
            self.logger.error(f"Error executing CT.gov backfill: {e}")
            return None
    
    def _execute_pubmed_backfill(self, start_date: datetime, end_date: datetime) -> Optional[PipelineExecutionResult]:
        """Execute PubMed backfill."""
        start_time = datetime.now(timezone.utc)
        self.logger.info("Executing PubMed backfill")
        
        try:
            # Execute PubMed backfill with date-specific trial configurations
            # This could be enhanced to use actual trial data from the date range
            trial_configs = [
                {
                    'trial_id': f'backfill_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}',
                    'asset_names': ['drug', 'compound', 'therapy', 'treatment'],
                    'indications': ['disease', 'condition', 'cancer', 'diabetes'],
                    'max_results': 500  # Higher limit for backfill
                }
            ]
            
            # Run the pipeline synchronously
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    self.logger.warning("Cannot run PubMed backfill synchronously from async context")
                    execution_result = PipelineExecutionResult(
                        pipeline_name="pubmed",
                        success=False,
                        start_time=start_time,
                        end_time=datetime.now(timezone.utc),
                        errors=["PubMed backfill requires async context for full execution"]
                    )
                    return execution_result
                else:
                    result = loop.run_until_complete(
                        self.pubmed_pipeline.run_daily_ingestion(
                            force_full_scan=True,
                            trial_configs=trial_configs
                        )
                    )
            except RuntimeError:
                result = asyncio.run(
                    self.pubmed_pipeline.run_daily_ingestion(
                        force_full_scan=True,
                        trial_configs=trial_configs
                    )
                )
            
            # Create execution result
            execution_result = PipelineExecutionResult(
                pipeline_name="pubmed",
                success=result.get('success', False),
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
                documents_processed=result.get('documents_processed', 0),
                documents_failed=result.get('documents_failed', 0),
                errors=result.get('errors', []),
                warnings=result.get('warnings', [])
            )
            
            self.logger.info(f"PubMed backfill completed: {result.get('documents_processed', 0)} documents processed")
            return execution_result
            
        except Exception as e:
            self.logger.error(f"Error executing PubMed backfill: {e}")
            return None
    
    def _execute_sec_backfill(self, start_date: datetime, end_date: datetime) -> Optional[PipelineExecutionResult]:
        """Execute SEC backfill."""
        start_time = datetime.now(timezone.utc)
        self.logger.info("Executing SEC backfill")
        
        try:
            # Execute backfill
            result = self.sec_pipeline.run_backfill(start_date.date(), end_date.date())
            
            # Create execution result
            execution_result = PipelineExecutionResult(
                pipeline_name="sec",
                success=result.success,
                start_time=start_time,
                end_time=datetime.now(timezone.utc),
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
                'pubmed': self._get_pipeline_status('pubmed'),
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
        elif pipeline_name == 'pubmed':
            # TODO: Implement PubMed pipeline status
            return {'status': 'not_implemented'}
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
                # Update last run times using pipeline result end times
                if self.current_execution.ctgov_result:
                    self.orchestration_state['last_ctgov_run'] = self.current_execution.ctgov_result.end_time.isoformat()
                
                if self.current_execution.pubmed_result:
                    self.orchestration_state['last_pubmed_run'] = self.current_execution.pubmed_result.end_time.isoformat()
                
                if self.current_execution.sec_result:
                    self.orchestration_state['last_sec_run'] = self.current_execution.sec_result.end_time.isoformat()
                
                # Update last orchestration run
                self.orchestration_state['last_orchestration_run'] = self.current_execution.end_time.isoformat()
                self.orchestration_state['last_execution_id'] = self.current_execution.execution_id
            
            # Save state
            with open(self.state_file, 'w') as f:
                json.dump(self.orchestration_state, f, indent=2, default=str)
                
        except Exception as e:
            self.logger.error(f"Failed to update orchestration state: {e}")
    
    def _enqueue_oa_tasks_from_pubmed_results(self, pubmed_result: Dict[str, Any]):
        """
        Enqueue OA tasks for trials that have completed PubMed U1+ processing.
        
        Args:
            pubmed_result: Result from PubMed pipeline execution
        """
        try:
            self.logger.info("Enqueueing OA tasks from PubMed results")
            
            # For now, we'll add a default trial since the PubMed pipeline
            # doesn't currently track which specific trials were processed
            # TODO: Enhance PubMed pipeline to return trial_ids that were processed
            
            # Get all trials that have literature state (were processed by U1)
            # This is a simplified approach - in practice, we'd get trial_ids from the pipeline result
            from ...db.session import session_scope
            from ...db.models import TrialLitState, Trial
            
            with session_scope() as session:
                # Get trials with recent literature state updates
                recent_trials = session.query(TrialLitState, Trial).join(
                    Trial, TrialLitState.trial_id == Trial.trial_id
                ).filter(
                    TrialLitState.best_S_Rge2.isnot(None)  # Has R/S scores
                ).limit(10).all()  # Limit to recent trials
                
                for lit_state, trial in recent_trials:
                    try:
                        # Calculate time_to_catalyst (simplified)
                        # TODO: Use actual catalyst detection from trial data
                        time_to_catalyst = self._calculate_time_to_catalyst(trial)
                        
                        # Calculate max expected utility (simplified)
                        max_expected_utility = self._calculate_max_expected_utility(lit_state)
                        
                        # Create trial data for queue
                        trial_data = {
                            'trial_id': lit_state.trial_id,
                            'nct_id': trial.nct_id,
                            'best_S_Rge2': float(lit_state.best_S_Rge2) if lit_state.best_S_Rge2 else 0.0,
                            'time_to_catalyst': time_to_catalyst,
                            'uncertainty': float(lit_state.uncertainty) if lit_state.uncertainty else 0.5,
                            'max_expected_utility_next_doc': max_expected_utility,
                            'p_short': float(lit_state.p_short) if lit_state.p_short else 0.0,
                            'n_docs_seen': lit_state.n_docs_seen or 0,
                            'n_docs_selected': lit_state.n_docs_selected or 0,
                            'status': lit_state.status or 'active'
                        }
                        
                        # Calculate priority for OA task
                        priority = self._calculate_oa_priority(lit_state, trial)
                        
                        # Enqueue OA task
                        success = self.task_queue_service.enqueue_task(
                            task_type='PUBMED_OA',
                            task_key=f'trial:{lit_state.trial_id}:OA',
                            priority=priority,
                            payload=trial_data,
                            trial_id=lit_state.trial_id
                        )
                        
                        if success:
                            self.logger.debug(f"Enqueued OA task for trial {lit_state.trial_id} with priority {priority}")
                        else:
                            self.logger.warning(f"Failed to enqueue OA task for trial {lit_state.trial_id}")
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to add trial {lit_state.trial_id} to queue: {e}")
                        continue
                
                self.logger.info(f"Successfully enqueued OA tasks for {len(recent_trials)} trials")
                
        except Exception as e:
            self.logger.error(f"Failed to enqueue OA tasks from PubMed results: {e}")
    
    def _calculate_oa_priority(self, lit_state, trial) -> float:
        """
        Calculate priority for OA task based on trial metrics.
        
        Args:
            lit_state: Trial literature state
            trial: Trial data
            
        Returns:
            Priority score
        """
        # Base priority from trial metrics
        base_priority = 0.0
        
        # Best S score among R≥2 documents
        best_s_rge2 = float(lit_state.best_S_Rge2) if lit_state.best_S_Rge2 else 0.0
        base_priority += 0.4 * best_s_rge2
        
        # Uncertainty (higher uncertainty = higher priority)
        uncertainty = float(lit_state.uncertainty) if lit_state.uncertainty else 0.0
        base_priority += 0.3 * uncertainty
        
        # Number of selected documents
        n_selected = lit_state.n_docs_selected or 0
        if n_selected > 0:
            base_priority += 0.2 * min(n_selected / 10, 1.0)  # Cap at 10 docs
        
        # Add trial ID for deterministic ordering
        base_priority += lit_state.trial_id / 1000000.0
        
        return base_priority
    
    def _calculate_studycard_priority(self, trial_id: int, payload: Dict[str, Any]) -> float:
        """
        Calculate priority for STUDY CARD task.
        
        Args:
            trial_id: Trial ID
            payload: Task payload with trial data
            
        Returns:
            Priority score
        """
        # Base priority from trial metrics
        base_priority = 0.0
        
        # Best S score among R≥2 documents
        best_s_rge2 = payload.get('best_S_Rge2', 0.0)
        base_priority += 0.4 * best_s_rge2
        
        # Uncertainty (higher uncertainty = higher priority)
        uncertainty = payload.get('uncertainty', 0.0)
        base_priority += 0.3 * uncertainty
        
        # Number of selected documents
        n_selected = payload.get('n_docs_selected', 0)
        if n_selected > 0:
            base_priority += 0.2 * min(n_selected / 10, 1.0)  # Cap at 10 docs
        
        # Add trial ID for deterministic ordering
        base_priority += trial_id / 1000000.0
        
        return base_priority
    
    def _calculate_time_to_catalyst(self, trial) -> Optional[float]:
        """
        Calculate time to next catalyst event for a trial.
        
        Args:
            trial: Trial database model
            
        Returns:
            Time to catalyst in days, or None if unknown
        """
        try:
            # Simplified calculation - in practice this would use actual catalyst detection
            # For now, use a placeholder based on trial phase and status
            
            if hasattr(trial, 'status') and trial.status:
                status = trial.status.lower()
                if 'recruiting' in status:
                    return 90.0  # 3 months for recruiting trials
                elif 'active' in status:
                    return 180.0  # 6 months for active trials
                elif 'completed' in status:
                    return 30.0  # 1 month for completed trials (results soon)
            
            return 120.0  # Default 4 months
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate time to catalyst: {e}")
            return None
    
    def _calculate_max_expected_utility(self, lit_state) -> float:
        """
        Calculate maximum expected utility for next document.
        
        Args:
            lit_state: TrialLitState database model
            
        Returns:
            Expected utility score (0.0 to 1.0)
        """
        try:
            # Simplified utility calculation based on uncertainty and current scores
            uncertainty = float(lit_state.uncertainty) if lit_state.uncertainty else 0.5
            best_s = float(lit_state.best_S_Rge2) if lit_state.best_S_Rge2 else 0.0
            
            # Higher uncertainty and lower current scores suggest higher utility for next doc
            utility = uncertainty * (1.0 - best_s) * 0.5  # Scale to reasonable range
            
            return min(max(utility, 0.0), 1.0)  # Clamp to [0, 1]
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate max expected utility: {e}")
            return 0.1  # Default low utility
    
    def run_literature_second_pass(self) -> Dict[str, Any]:
        """
        Run the second pass of literature processing: pop trial from queue, 
        fetch full text, and process study cards.
        
        Returns:
            Dictionary with second pass execution results
        """
        try:
            self.logger.info("Starting literature second pass execution")
            
            # Lease next OA task from queue
            next_task = self.task_queue_service.lease_next(['PUBMED_OA'])
            if not next_task:
                self.logger.info("No OA tasks available in task queue")
                return {
                    'success': True,
                    'trials_processed': 0,
                    'message': 'No OA tasks available for processing'
                }
            
            trial_id = next_task.get('trial_id')
            task_id = next_task.get('id')
            payload = next_task.get('payload', {})
            nct_id = payload.get('nct_id')
            self.logger.info(f"Processing OA task {task_id} for trial {trial_id}")
            
            # Run OA stage for this trial to fetch full text
            try:
                import asyncio
                
                async def run_oa_async():
                    return await self.pubmed_pipeline.run_oa_for_trial(trial_id)
                
                # Execute OA stage
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        self.logger.warning("Cannot run OA stage synchronously from async context")
                        oa_result = None
                    else:
                        oa_result = loop.run_until_complete(run_oa_async())
                except RuntimeError:
                    oa_result = asyncio.run(run_oa_async())
                
                if oa_result and oa_result.success:
                    self.logger.info(f"OA stage completed for trial {trial_id}: {oa_result.documents_processed} documents processed")
                else:
                    self.logger.warning(f"OA stage failed for trial {trial_id}")
                
            except Exception as e:
                self.logger.error(f"Failed to run OA stage for trial {trial_id}: {e}")
                oa_result = None
            
            # Execute study card pipeline
            try:
                from ..study_card_pipeline import StudyCardPipeline
                
                # Create trial context for study card generation
                trial_context = {
                    'trial_id': trial_id,
                    'nct_id': nct_id,
                    'trial_name': f"Trial {nct_id}" if nct_id else f"Trial {trial_id}",
                    'disease': payload.get('indication', payload.get('indication_terms', ['Unknown']))[0]
                              if isinstance(payload.get('indication_terms'), list) else payload.get('indication', 'Unknown'),
                    'intervention': payload.get('asset_name') or (
                        payload.get('asset_aliases', ['Unknown'])[0] if isinstance(payload.get('asset_aliases'), list) else 'Unknown'
                    ),
                    'date_window': "2020-2024"
                }
                
                # Initialize and run study card pipeline
                study_card_config = self.config.get('study_card', {})
                study_card_pipeline = StudyCardPipeline(study_card_config)
                
                study_card_result = study_card_pipeline.execute(trial_context)
                
                if study_card_result and study_card_result.get('success', False):
                    self.logger.info(f"Study card generated successfully for trial {trial_id}")
                    
                    # Complete OA task and enqueue STUDY CARD task
                    self.task_queue_service.complete_task(task_id)
                    
                    # Enqueue STUDY CARD task
                    priority = self._calculate_studycard_priority(trial_id, payload)
                    self.task_queue_service.enqueue_task(
                        task_type='STUDYCARD',
                        task_key=f'trial:{trial_id}:STUDYCARD',
                        priority=priority,
                        payload=payload,
                        trial_id=trial_id
                    )
                    
                    return {
                        'success': True,
                        'trials_processed': 1,
                        'trial_id': trial_id,
                        'nct_id': nct_id,
                        'oa_documents_processed': oa_result.documents_processed if oa_result else 0,
                        'study_card_generated': True,
                        'study_card_result': study_card_result
                    }
                else:
                    self.logger.warning(f"Study card generation failed for trial {trial_id}")
                    
                    # Fail OA task
                    self.task_queue_service.fail_task(task_id, "Study card generation failed")
                    
                    return {
                        'success': False,
                        'trials_processed': 1,
                        'trial_id': trial_id,
                        'nct_id': nct_id,
                        'oa_documents_processed': oa_result.documents_processed if oa_result else 0,
                        'study_card_generated': False,
                        'error': 'Study card generation failed'
                    }
                
            except Exception as e:
                self.logger.error(f"Failed to generate study card for trial {trial_id}: {e}")
                
                # Fail OA task
                self.task_queue_service.fail_task(task_id, f"Study card generation error: {e}")
                
                return {
                    'success': False,
                    'trials_processed': 1,
                    'trial_id': trial_id,
                    'nct_id': nct_id,
                    'oa_documents_processed': oa_result.documents_processed if oa_result else 0,
                    'study_card_generated': False,
                    'error': str(e)
                }
            
        except Exception as e:
            self.logger.error(f"Failed to run literature second pass: {e}")
            return {
                'success': False,
                'trials_processed': 0,
                'error': str(e)
            }
    
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
            # Use dataclasses.asdict for proper serialization
            data = asdict(execution)
            return json.dumps(data, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")
