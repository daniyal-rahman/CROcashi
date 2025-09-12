"""
PubMed Pipeline for automated literature ingestion and processing.

This module provides:
- Automated PubMed literature discovery and ingestion
- Multi-tier query building and execution
- Dual persistence (raw + processed documents)
- Integration with entity resolution
- Study card generation triggering
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator
import json
from dataclasses import dataclass, field

from ..ingest.pubmed.pipeline_dual_persistence import PubMedPipelineDualPersistence
from ..ingest.pubmed.db_service import PubMedDBService
from ..ingest.pubmed.queue_service import TaskQueueService
from ..ingest.pubmed.retrieval.policy_engine import RetrievalPolicy, PolicyConfig
from ..ingest.pubmed.retrieval.query_builder import MultiTierQueryBuilder
from ..ingest.pubmed.retrieval.document_scorer import AdvancedDocumentScorer, ScoringConfig
from ..ingest.pubmed.retrieval.guardrails import GuardrailsSystem, GuardrailConfig
from ..ingest.pubmed.retrieval.ctgov_discovery import CTgovIntegration, CTgovConfig
from ..db.session import get_session
from ..db.models import Trial, Document, DocumentLink
from ..config import get_config

logger = logging.getLogger(__name__)


@dataclass
class PubMedPipelineResult:
    """Result of PubMed pipeline execution."""
    success: bool
    start_time: datetime
    end_time: datetime
    processing_time_seconds: float = field(init=False, default=0.0)
    
    # Pipeline-specific metrics
    documents_processed: int = 0
    documents_failed: int = 0
    retrieval_documents: int = 0
    processed_documents: int = 0
    sessions_created: int = 0
    
    # Query metrics
    queries_executed: int = 0
    total_pmids_found: int = 0
    unique_pmids: int = 0
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Calculate processing time."""
        if self.end_time and self.start_time:
            self.processing_time_seconds = (self.end_time - self.start_time).total_seconds()


class PubMedPipeline:
    """PubMed literature ingestion and processing pipeline."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize PubMed pipeline with configuration."""
        self.config = config
        self.pubmed_config = config
        
        # Pipeline state
        self.pipeline_results: List[PubMedPipelineResult] = []
        self.current_execution: Optional[PubMedPipelineResult] = None
        
        # Initialize components
        self._initialize_components()
        
        logger.info("PubMed Pipeline initialized")
    
    def _initialize_components(self):
        """Initialize PubMed pipeline components."""
        try:
            # Initialize dual persistence pipeline
            self.pipeline = PubMedPipelineDualPersistence(
                self.pubmed_config,
                get_session
            )
            
            # Initialize services
            self.db_service = PubMedDBService()
            self.queue_service = TaskQueueService()
            
            logger.info("Successfully initialized PubMed components")
            
        except Exception as e:
            logger.error(f"Error initializing PubMed components: {e}")
            raise
    
    async def execute(self, 
                     trial_ids: Optional[List[int]] = None,
                     asset_names: Optional[List[str]] = None,
                     indications: Optional[List[str]] = None,
                     max_results: int = 1000,
                     trial_nct_ids: Optional[List[str]] = None,
                     trial_phases: Optional[List[str]] = None,
                     company_names: Optional[List[str]] = None) -> PubMedPipelineResult:
        """
        Execute PubMed pipeline for specified trials.
        
        Args:
            trial_ids: List of trial IDs to process
            asset_names: List of asset names to search for
            indications: List of indications to search for
            max_results: Maximum number of results to process
            trial_nct_ids: List of NCT IDs for Query D
            trial_phases: List of trial phases
            company_names: List of company names
            
        Returns:
            PubMedPipelineResult with execution details
        """
        start_time = datetime.now(timezone.utc)
        logger.info(f"Starting PubMed pipeline execution for {len(trial_ids) if trial_ids else 'all'} trials")
        
        try:
            # Get trials to process
            if trial_ids is None:
                with get_session() as session:
                    trials = session.query(Trial).all()
                    trial_ids = [t.trial_id for t in trials]
            
            # Process each trial
            total_documents = 0
            total_errors = []
            total_warnings = []
            sessions_created = 0
            
            for i, trial_id in enumerate(trial_ids):
                try:
                    logger.info(f"Processing trial {trial_id}...")
                    
                    # Get NCT ID and other data for this trial
                    trial_nct = trial_nct_ids[i] if trial_nct_ids and i < len(trial_nct_ids) else None
                    trial_phase = trial_phases[i] if trial_phases and i < len(trial_phases) else None
                    company_name = company_names[i] if company_names and i < len(company_names) else None
                    
                    # Execute dual persistence pipeline
                    results = await self.pipeline.execute_pipeline(
                        trial_id=trial_id,
                        asset_names=asset_names,
                        indications=indications,
                        max_results=max_results,
                        enable_stages=['retrieval', 'processing'],
                        trial_nct=trial_nct,
                        trial_phase=trial_phase,
                        company_name=company_name
                    )
                    
                    # Aggregate results
                    for result in results:
                        if result.success:
                            total_documents += result.documents_processed
                        if result.errors:
                            total_errors.extend(result.errors)
                        if result.warnings:
                            total_warnings.extend(result.warnings)
                    
                    sessions_created += 1
                    
                except Exception as e:
                    error_msg = f"Error processing trial {trial_id}: {str(e)}"
                    logger.error(error_msg)
                    total_errors.append(error_msg)
            
            # Get retrieval metrics
            retrieval_docs = 0
            processed_docs = 0
            for trial_id in trial_ids:
                try:
                    retrieval_docs += len(await self.pipeline.get_retrieval_documents(trial_id))
                    processed_docs += len(await self.pipeline.get_processed_documents(trial_id))
                except Exception:
                    pass  # Ignore errors getting metrics
            
            end_time = datetime.now(timezone.utc)
            
            result = PubMedPipelineResult(
                success=len(total_errors) == 0,
                start_time=start_time,
                end_time=end_time,
                documents_processed=total_documents,
                retrieval_documents=retrieval_docs,
                processed_documents=processed_docs,
                sessions_created=sessions_created,
                errors=total_errors,
                warnings=total_warnings
            )
            
            # Store result
            self.pipeline_results.append(result)
            self.current_execution = result
            
            logger.info(f"PubMed pipeline completed: {total_documents} documents processed, {len(total_errors)} errors")
            return result
            
        except Exception as e:
            error_msg = f"PubMed pipeline execution failed: {str(e)}"
            logger.error(error_msg)
            
            end_time = datetime.now(timezone.utc)
            result = PubMedPipelineResult(
                success=False,
                start_time=start_time,
                end_time=end_time,
                errors=[error_msg]
            )
            
            # Store result
            self.pipeline_results.append(result)
            self.current_execution = result
            
            return result
    
    def get_retrieval_metrics(self, trial_id: int) -> Dict[str, Any]:
        """Get retrieval metrics for a specific trial."""
        try:
            return self.pipeline.get_retrieval_metrics(trial_id)
        except Exception as e:
            logger.error(f"Error getting retrieval metrics for trial {trial_id}: {e}")
            return {}
    
    def get_retrieval_documents(self, trial_id: int) -> List[Dict[str, Any]]:
        """Get retrieval documents for a specific trial."""
        try:
            return self.pipeline.get_retrieval_documents(trial_id)
        except Exception as e:
            logger.error(f"Error getting retrieval documents for trial {trial_id}: {e}")
            return []
    
    def get_processed_documents(self, trial_id: int) -> List[Dict[str, Any]]:
        """Get processed documents for a specific trial."""
        try:
            return self.pipeline.get_processed_documents(trial_id)
        except Exception as e:
            logger.error(f"Error getting processed documents for trial {trial_id}: {e}")
            return []
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update pipeline configuration with validation."""
        try:
            # Update main config
            self.config.update(new_config)
            
            # Update PubMed-specific config
            if 'pubmed' in new_config:
                self.pubmed_config.update(new_config['pubmed'])
            
            # Reinitialize components if needed
            if any(key in new_config for key in ['client_config', 'retrieval_config', 'processing_config']):
                self._initialize_components()
            
            logger.info("Pipeline configuration updated successfully")
            
        except Exception as e:
            logger.error(f"Error updating pipeline configuration: {e}")
            raise
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration."""
        return {
            'pipeline_type': 'PubMed',
            'max_results': self.pubmed_config.get('max_results', 1000),
            'enable_stages': self.pubmed_config.get('enable_stages', ['retrieval', 'processing']),
            'client_config': self.pubmed_config.get('client_config', {}),
            'retrieval_config': self.pubmed_config.get('retrieval_config', {}),
            'processing_config': self.pubmed_config.get('processing_config', {})
        }
    
    def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get summary of pipeline execution."""
        if not self.pipeline_results:
            return {'status': 'not_started'}
        
        successful_executions = [r for r in self.pipeline_results if r.success]
        failed_executions = [r for r in self.pipeline_results if not r.success]
        
        total_docs_processed = sum(r.documents_processed for r in successful_executions)
        total_docs_failed = sum(r.documents_failed for r in self.pipeline_results)
        total_execution_time = sum(r.processing_time_seconds for r in self.pipeline_results)
        
        return {
            'status': 'completed' if not failed_executions else 'partial_failure',
            'executions_completed': len(successful_executions),
            'executions_failed': len(failed_executions),
            'total_documents_processed': total_docs_processed,
            'total_documents_failed': total_docs_failed,
            'total_execution_time': total_execution_time,
            'retrieval_documents': sum(r.retrieval_documents for r in successful_executions),
            'processed_documents': sum(r.processed_documents for r in successful_executions),
            'sessions_created': sum(r.sessions_created for r in successful_executions)
        }
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status for orchestrator."""
        return {
            'status': 'ready' if self.pipeline_results else 'not_started',
            'executions_completed': len([r for r in self.pipeline_results if r.success]),
            'executions_failed': len([r for r in self.pipeline_results if not r.success]),
            'total_documents_processed': sum(r.documents_processed for r in self.pipeline_results if r.success),
            'last_execution': self.pipeline_results[-1].end_time if self.pipeline_results else None
        }
    
    async def run_daily_ingestion(self, 
                                 force_full_scan: bool = False,
                                 max_trials: Optional[int] = None) -> PubMedPipelineResult:
        """
        Run daily PubMed ingestion for all trials.
        
        Args:
            force_full_scan: Whether to force a full scan regardless of last run
            max_trials: Maximum number of trials to process
            
        Returns:
            PubMedPipelineResult with execution details
        """
        logger.info(f"Starting daily PubMed ingestion (force_full_scan={force_full_scan})")
        
        # Get trials to process
        with get_session() as session:
            query = session.query(Trial)
            if not force_full_scan:
                # Only process trials updated in the last 24 hours
                cutoff_time = datetime.now(timezone.utc) - timedelta(days=1)
                query = query.filter(Trial.updated_at >= cutoff_time)
            
            if max_trials:
                query = query.limit(max_trials)
            
            trials = query.all()
            trial_ids = [t.trial_id for t in trials]
        
        logger.info(f"Found {len(trial_ids)} trials to process")
        
        # Execute pipeline for all trials
        return await self.execute(trial_ids=trial_ids)
    
    async def search_literature_for_trial(self, 
                                        trial_id: int,
                                        nct_id: Optional[str] = None,
                                        trial_data: Optional[Dict[str, Any]] = None,
                                        max_results: int = 100) -> Dict[str, Any]:
        """
        Search literature for a specific trial.
        
        Args:
            trial_id: Trial ID
            nct_id: NCT ID for the trial
            trial_data: Additional trial data
            max_results: Maximum number of results
            
        Returns:
            Dictionary with search results
        """
        try:
            # Extract asset names and indications from trial data
            asset_names = []
            indications = []
            
            if trial_data:
                # Extract from trial data if available
                asset_names = trial_data.get('asset_names', [])
                indications = trial_data.get('indications', [])
            
            # If no data provided, try to get from database
            if not asset_names or not indications:
                with get_session() as session:
                    trial = session.query(Trial).filter(Trial.trial_id == trial_id).first()
                    if trial:
                        # Extract from trial title and description
                        if not asset_names:
                            # Simple extraction - could be enhanced
                            asset_names = [trial.title] if trial.title else []
                        if not indications:
                            indications = [trial.title] if trial.title else []
            
            # Execute pipeline
            result = await self.execute(
                trial_ids=[trial_id],
                asset_names=asset_names,
                indications=indications,
                max_results=max_results
            )
            
            return {
                'trial_id': trial_id,
                'nct_id': nct_id,
                'success': result.success,
                'documents_processed': result.documents_processed,
                'retrieval_documents': result.retrieval_documents,
                'processed_documents': result.processed_documents,
                'errors': result.errors,
                'warnings': result.warnings
            }
            
        except Exception as e:
            logger.error(f"Error searching literature for trial {trial_id}: {e}")
            return {
                'trial_id': trial_id,
                'nct_id': nct_id,
                'success': False,
                'documents_processed': 0,
                'retrieval_documents': 0,
                'processed_documents': 0,
                'errors': [str(e)],
                'warnings': []
            }
