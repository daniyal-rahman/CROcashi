"""
PubMed Pipeline - Dual Persistence Strategy.

Implements the dual persistence strategy:
1. Retrieval: Find ALL documents and store them (human verification)
2. Processing: Filter and process documents for LLM consumption
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from .dual_persistence_service import DualPersistenceService
from .retrieval.retrieval_orchestrator import RetrievalOrchestrator
from .processing.abstract_processor import AbstractProcessor
from .db_service import PubMedDBService
from .queue_service import TaskQueueService
from ...db.retrieval_models import RetrievalSession, RetrievalDocument, ProcessedDocument

logger = logging.getLogger(__name__)


@dataclass
class PipelineExecutionResult:
    """Result from pipeline execution."""
    success: bool
    trial_id: int
    session_id: str
    documents_processed: int
    retrieval_documents: int
    processed_documents: int
    execution_time_seconds: float
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class PubMedPipelineDualPersistence:
    """End-to-end PubMed literature processing pipeline with dual persistence."""
    
    def __init__(self, config: Dict[str, Any], session_factory=None):
        """Initialize PubMed pipeline with dual persistence."""
        self.config = config
        self.session_factory = session_factory
        
        # Extract configuration
        self.asset_names = config.get('asset_names', [])
        self.indications = config.get('indications', [])
        self.client_config = config.get('client_config', {})
        self.rerank_config = config.get('rerank_config', {})
        self.policy_config = config.get('policy_config', {})
        self.scoring_config = config.get('scoring_config', {})
        self.guardrail_config = config.get('guardrail_config', {})
        self.ctgov_config = config.get('ctgov_config', {})
        
        # Initialize components
        self.dual_persistence_service = DualPersistenceService(config)
        self.retrieval_orchestrator = RetrievalOrchestrator(config, session_factory)
        self.abstract_processor = AbstractProcessor(config, session_factory)
        self.db_service = PubMedDBService()
        self.queue_service = TaskQueueService()
        
        self._validate_config()
        logger.info("PubMed Pipeline with dual persistence initialized")
    
    def _validate_config(self):
        """Validate pipeline configuration."""
        required_keys = ['asset_names', 'indications']
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"Missing required configuration key: {key}")
        
        if not self.config['asset_names']:
            raise ValueError("asset_names cannot be empty")
        if not self.config['indications']:
            raise ValueError("indications cannot be empty")
    
    async def execute_pipeline(
        self,
        trial_id: int,
        asset_names: Optional[List[str]] = None,
        indications: Optional[List[str]] = None,
        max_results: int = 1000,
        enable_stages: List[str] = None,
        trial_nct: Optional[str] = None,
        trial_phase: Optional[str] = None,
        company_name: Optional[str] = None,
        company_aliases: Optional[List[str]] = None
    ) -> List[PipelineExecutionResult]:
        """
        Execute the complete PubMed pipeline with dual persistence.
        
        Args:
            trial_id: Trial ID to process
            asset_names: Asset names to search for (overrides config)
            indications: Indications to search for (overrides config)
            max_results: Maximum number of results to process
            enable_stages: List of stages to enable ['retrieval', 'processing']
            trial_nct: Optional NCT ID for Query D
            trial_phase: Optional trial phase
            company_name: Optional company name
            company_aliases: Optional company aliases
            
        Returns:
            List of PipelineExecutionResult objects
        """
        if enable_stages is None:
            enable_stages = ['retrieval', 'processing']
        
        start_time = datetime.now(timezone.utc)
        # Don't create session_id here - let retrieval orchestrator create it
        
        # Use provided values or fall back to config
        asset_names = asset_names or self.asset_names
        indications = indications or self.indications
        
        logger.info(f"Starting PubMed pipeline execution for trial {trial_id}")
        logger.info(f"Asset names: {asset_names}")
        logger.info(f"Indications: {indications}")
        logger.info(f"Max results: {max_results}")
        logger.info(f"Enabled stages: {enable_stages}")
        
        # Check for existing documents first
        existing_count = await self._check_existing_documents(trial_id)
        min_required = self.config.get('min_documents_required', 1)
        skip_if_sufficient = self.config.get('skip_if_sufficient', False)
        
        if existing_count >= min_required and skip_if_sufficient:
            logger.info(f"Found {existing_count} existing documents for trial {trial_id}, skipping retrieval")
            
            # Get existing documents for processing
            existing_docs = await self.dual_persistence_service.get_existing_documents(trial_id)
            
            return [PipelineExecutionResult(
                success=True,
                trial_id=trial_id,
                session_id="reused",  # Indicate this was reused
                documents_processed=len(existing_docs),
                retrieval_documents=existing_count,
                processed_documents=len(existing_docs),
                execution_time_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                errors=[],
                warnings=[f"Reused {existing_count} existing documents"]
            )]
        
        results = []
        errors = []
        warnings = []
        
        try:
            # Note: Don't create retrieval session here - let retrieval orchestrator handle it
            
            # Stage 1: Retrieval (Steps 1-6)
            if 'retrieval' in enable_stages:
                logger.info("Starting retrieval stage...")
                retrieval_result = await self.retrieval_orchestrator.execute_retrieval(
                    trial_id=trial_id,
                    asset_aliases=asset_names,
                    indication_terms=indications,
                    trial_nct=trial_nct,
                    trial_phase=trial_phase,
                    company_name=company_name,
                    company_aliases=company_aliases,
                    max_results=max_results
                )
                
                if not retrieval_result.success:
                    errors.append(f"Retrieval failed: {retrieval_result.error_message}")
                    return [PipelineExecutionResult(
                        success=False,
                        trial_id=trial_id,
                        session_id=session_id,
                        documents_processed=0,
                        retrieval_documents=0,
                        processed_documents=0,
                        execution_time_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                        errors=errors,
                        warnings=warnings
                    )]
                
                # Get session ID from retrieval result
                session_id = retrieval_result.session_id
                
                # Store retrieval documents
                retrieval_docs_stored = await self.dual_persistence_service.store_retrieval_documents(
                    trial_id=trial_id,
                    session_id=session_id,
                    documents=retrieval_result.documents
                )
                
                logger.info(f"Retrieved and stored {retrieval_docs_stored} documents")
                logger.error(f"DEBUG: retrieval_docs_stored = {retrieval_docs_stored}")
                
                # Update session with retrieval metrics
                await self.dual_persistence_service.update_session_completion(
                    session_id=session_id,
                    total_documents_found=retrieval_result.documents_discovered,
                    documents_after_policy_engine=retrieval_result.documents_mapped,
                    documents_after_guardrails=retrieval_result.documents_mapped,  # Same as policy engine for now
                    documents_after_processing=0,  # Will be updated after processing
                    execution_time_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                    status='running'
                )
            else:
                retrieval_docs_stored = 0
                logger.info("Skipping retrieval stage")
            
            # Stage 2: Processing (Steps 7-9)
            processed_docs_stored = 0  # Initialize in case processing fails
            logger.error(f"DEBUG: enable_stages = {enable_stages}, retrieval_docs_stored = {retrieval_docs_stored}")
            
            # Check if we have any retrieval documents available for processing
            existing_retrieval_docs = await self.dual_persistence_service.get_retrieval_documents(trial_id)
            logger.error(f"DEBUG: Found {len(existing_retrieval_docs)} existing retrieval documents for trial {trial_id}")
            
            if 'processing' in enable_stages and len(existing_retrieval_docs) > 0:
                logger.info("Starting processing stage...")
                
                # Use the existing retrieval documents for processing
                raw_documents = existing_retrieval_docs
                
                processing_result = await self.abstract_processor.process_documents(
                    documents=raw_documents,
                    trial_id=trial_id,
                    trial_asset=asset_names[0] if asset_names else "unknown",
                    trial_indication=indications[0] if indications else "unknown",
                    trial_nct=trial_nct
                )
                
                if not processing_result.success:
                    errors.append(f"Processing failed: {processing_result.error_message}")
                else:
                    # Store processed documents
                    processed_docs_stored = await self.dual_persistence_service.store_processed_documents(
                        trial_id=trial_id,
                        documents=processing_result.processed_documents
                    )
                    
                    logger.info(f"Processed and stored {processed_docs_stored} documents")
                    
                    # Update session with final metrics
                    await self.dual_persistence_service.update_session_completion(
                        session_id=session_id,
                        total_documents_found=retrieval_docs_stored,
                        documents_after_policy_engine=retrieval_docs_stored,
                        documents_after_guardrails=retrieval_docs_stored,
                        documents_after_processing=processed_docs_stored,
                        execution_time_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                        status='completed'
                    )
            else:
                processed_docs_stored = 0
                logger.info("Skipping processing stage")
            
            # Create final result
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            result = PipelineExecutionResult(
                success=True,
                trial_id=trial_id,
                session_id=session_id,
                documents_processed=retrieval_docs_stored + processed_docs_stored,
                retrieval_documents=retrieval_docs_stored,
                processed_documents=processed_docs_stored,
                execution_time_seconds=execution_time,
                errors=errors,
                warnings=warnings
            )
            
            results.append(result)
            
            logger.info(f"Pipeline execution completed for trial {trial_id}")
            logger.info(f"Retrieval documents: {retrieval_docs_stored}")
            logger.info(f"Processed documents: {processed_docs_stored}")
            logger.info(f"Total execution time: {execution_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Pipeline execution failed for trial {trial_id}: {e}")
            errors.append(str(e))
            
            result = PipelineExecutionResult(
                success=False,
                trial_id=trial_id,
                session_id=session_id,
                documents_processed=0,
                retrieval_documents=0,
                processed_documents=0,
                execution_time_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                errors=errors,
                warnings=warnings
            )
            results.append(result)
        
        return results
    
    async def _check_existing_documents(self, trial_id: int) -> int:
        """Check if sufficient documents already exist for this trial."""
        return await self.dual_persistence_service.get_existing_documents_count(trial_id)
    
    async def get_existing_documents_count(self, trial_id: int) -> int:
        """Get count of existing processed documents for a trial."""
        return await self.dual_persistence_service.get_existing_documents_count(trial_id)
    
    async def get_retrieval_metrics(self, trial_id: int) -> Dict[str, Any]:
        """Get retrieval metrics for a trial."""
        with self.session_factory() as session:
            # Get all retrieval sessions for this trial
            sessions = session.query(RetrievalSession).filter(
                RetrievalSession.trial_id == trial_id
            ).all()
            
            if not sessions:
                return {
                    'trial_id': trial_id,
                    'total_sessions': 0,
                    'total_documents_found': 0,
                    'total_retrieval_documents': 0,
                    'total_processed_documents': 0
                }
            
            # Get document counts
            retrieval_docs = session.query(RetrievalDocument).filter(
                RetrievalDocument.trial_id == trial_id
            ).count()
            
            processed_docs = session.query(ProcessedDocument).filter(
                ProcessedDocument.trial_id == trial_id
            ).count()
            
            return {
                'trial_id': trial_id,
                'total_sessions': len(sessions),
                'total_documents_found': sum(s.total_documents_found or 0 for s in sessions),
                'total_retrieval_documents': retrieval_docs,
                'total_processed_documents': processed_docs,
                'latest_session': {
                    'session_id': sessions[-1].session_id,
                    'status': sessions[-1].status,
                    'created_at': sessions[-1].created_at.isoformat(),
                    'completed_at': sessions[-1].completed_at.isoformat() if sessions[-1].completed_at else None
                }
            }
    
    async def get_retrieval_documents(self, trial_id: int) -> List[Dict[str, Any]]:
        """Get retrieval documents for a trial."""
        return await self.dual_persistence_service.get_retrieval_documents(trial_id)
    
    async def get_processed_documents(self, trial_id: int) -> List[Dict[str, Any]]:
        """Get processed documents for a trial."""
        return await self.dual_persistence_service.get_processed_documents(trial_id)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary."""
        return {
            'asset_names': self.asset_names,
            'indications': self.indications,
            'client_config': self.client_config,
            'rerank_config': self.rerank_config,
            'policy_config': self.policy_config,
            'scoring_config': self.scoring_config,
            'guardrail_config': self.guardrail_config,
            'ctgov_config': self.ctgov_config
        }
