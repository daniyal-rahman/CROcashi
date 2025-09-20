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

# Dual persistence pipeline removed - using simplified approach
from ..ingest.pubmed.db_service import PubMedDBService
from ..ingest.pubmed.document_manager import DocumentManager
from ..ingest.pubmed.queue_service import TaskQueueService
from ..ingest.pubmed.retrieval.policy_engine import RetrievalPolicy, PolicyConfig
from ..ingest.pubmed.retrieval.query_builder import MultiTierQueryBuilder
from ..ingest.pubmed.retrieval.document_scorer import AdvancedDocumentScorer, ScoringConfig
from ..ingest.pubmed.retrieval.guardrails import GuardrailsSystem, GuardrailConfig
from ..ingest.pubmed.retrieval.ctgov_discovery import CTgovIntegration, CTgovConfig
from ..db.session import get_session, session_scope
from ..db.models import Trial, Document
from ..config import get_config

logger = logging.getLogger(__name__)


@dataclass
class PubMedPipelineOutput:
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
        self.pipeline_results: List[PubMedPipelineOutput] = []
        self.current_execution: Optional[PubMedPipelineOutput] = None
        
        # Initialize components
        self._initialize_components()
        
        logger.info("PubMed Pipeline initialized")
    
    def _initialize_components(self):
        """Initialize PubMed pipeline components."""
        try:
            # Using simplified approach - no separate pipeline needed
            self.pipeline = None
            
            # Initialize services
            self.db_service = PubMedDBService()
            self.document_manager = DocumentManager()
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
                     company_names: Optional[List[str]] = None,
                     entity_packs: Optional[List[Any]] = None) -> PubMedPipelineOutput:
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
            entity_packs: List of EntityPack objects from orchestrator
            
        Returns:
            PubMedPipelineOutput with execution details
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
                    entity_pack = entity_packs[i] if entity_packs and i < len(entity_packs) else None
                    
                    # Execute simplified pipeline using new components
                    from ..ingest.pubmed import RetrievalProcessor, AbstractProcessor
                    
                    retrieval_processor = RetrievalProcessor(self.config)
                    abstract_processor = AbstractProcessor(self.config)
                    
                    # Extract data from entity pack if available, otherwise use fallback parameters
                    if entity_pack:
                        asset_aliases = entity_pack.get_all_asset_terms()
                        indication_terms = entity_pack.get_all_indication_terms()
                        company_aliases = entity_pack.get_all_company_terms()
                        nct_ids = entity_pack.get_all_nct_ids()
                        
                        logger.info(f"Using entity pack for trial {trial_id}: {len(asset_aliases)} assets, {len(indication_terms)} indications")
                    else:
                        # Fallback to provided parameters
                        asset_aliases = asset_names or []
                        indication_terms = indications or []
                        company_aliases = company_names or []
                        nct_ids = [trial_nct] if trial_nct else []
                        
                        logger.info(f"Using fallback parameters for trial {trial_id}: {len(asset_aliases)} assets, {len(indication_terms)} indications")
                    
                    # Run retrieval
                    retrieval_result = await retrieval_processor.execute_retrieval(
                        trial_id=trial_id,
                        asset_aliases=asset_aliases,
                        indication_terms=indication_terms,
                        max_results=max_results,
                        trial_nct=trial_nct,
                        trial_phase=trial_phase,
                        company_name=company_name,
                        company_aliases=company_aliases,
                        entity_pack=entity_pack  # Pass the entity pack to avoid duplication
                    )
                    
                    if not retrieval_result.success:
                        error_msg = f"Retrieval failed for trial {trial_id}: {retrieval_result.error_message}"
                        logger.error(error_msg)
                        total_errors.append(error_msg)
                        continue
                    
                    # Run processing
                    processing_result = await abstract_processor.process_documents(
                        documents=retrieval_result.documents,
                        trial_id=trial_id,
                        trial_asset=asset_names[0] if asset_names else "unknown",
                        trial_indication=indications[0] if indications else "unknown",
                        trial_nct=trial_nct
                    )
                    
                    if processing_result.success:
                        total_documents += processing_result.documents_processed
                    else:
                        error_msg = f"Processing failed for trial {trial_id}: {processing_result.error_message}"
                        logger.error(error_msg)
                        total_errors.append(error_msg)
                    
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
                    counts = self.db_service.get_document_counts_by_stage(trial_id)
                    retrieval_docs += counts['total']
                    processed_docs += counts['processed']
                except Exception:
                    pass  # Ignore errors getting metrics
            
            end_time = datetime.now(timezone.utc)
            
            result = PubMedPipelineOutput(
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
            result = PubMedPipelineOutput(
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
            counts = self.db_service.get_document_counts_by_stage(trial_id)
            return {
                'total_documents': counts['total'],
                'processed_documents': counts['processed'],
                'raw_documents': counts['total'] - counts['processed']
            }
        except Exception as e:
            logger.error(f"Error getting retrieval metrics for trial {trial_id}: {e}")
            return {}
    
    def get_retrieval_documents(self, trial_id: int) -> List[Dict[str, Any]]:
        """Get retrieval documents for a specific trial."""
        try:
            # Return simplified document list from database
            with session_scope() as session:
                docs = session.query(Document).filter(
                    Document.trial_id == trial_id,
                    Document.processing_stage == 'raw'
                ).all()
                return [{'pmid': doc.pmid, 'title': doc.title, 'abstract': doc.abstract} for doc in docs]
        except Exception as e:
            logger.error(f"Error getting retrieval documents for trial {trial_id}: {e}")
            return []
    
    def get_processed_documents(self, trial_id: int) -> List[Dict[str, Any]]:
        """Get processed documents for a specific trial."""
        try:
            # Return simplified document list from database
            with session_scope() as session:
                docs = session.query(Document).filter(
                    Document.trial_id == trial_id,
                    Document.processing_stage == 'processed'
                ).all()
                return [{'pmid': doc.pmid, 'title': doc.title, 'abstract': doc.abstract} for doc in docs]
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
                                 max_trials: Optional[int] = None) -> PubMedPipelineOutput:
        """
        Run daily PubMed ingestion for all trials.
        
        Args:
            force_full_scan: Whether to force a full scan regardless of last run
            max_trials: Maximum number of trials to process
            
        Returns:
            PubMedPipelineOutput with execution details
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
                        # Extract comprehensive terms from trial data
                        if not asset_names:
                            asset_names = self._extract_comprehensive_asset_names(trial)
                        if not indications:
                            indications = self._extract_comprehensive_indications(trial)
            
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
    
    def _extract_comprehensive_asset_names(self, trial: Trial) -> List[str]:
        """
        Extract comprehensive asset names from trial data.
        
        Args:
            trial: Trial object from database
            
        Returns:
            List of comprehensive asset names and aliases
        """
        asset_names = []
        
        try:
            # Extract from trial title
            if trial.title:
                # Look for drug names in title
                title_lower = trial.title.lower()
                
                # Check for simufilam/PTI-125 patterns
                if 'simufilam' in title_lower or 'pti' in title_lower:
                    asset_names.extend([
                        'simufilam', 'Simufilam', 'SIMUFILAM',
                        'PTI-125', 'PTI 125', 'PTI125', 'PTI_125',
                        'PTI-125HCl', 'PTI-125 HCl',
                        'filamin A inhibitor', 'FLNA inhibitor', 'filamin-A inhibitor'
                    ])
                
                # Extract other drug names from title
                words = trial.title.split()
                for word in words:
                    if len(word) > 3 and word.isalpha():
                        # Simple heuristic for drug names (capitalized, not common words)
                        if word[0].isupper() and word.lower() not in ['study', 'patients', 'with', 'phase', 'trial', 'clinical']:
                            asset_names.append(word)
            
            # Extract from trial description if available
            if trial.description:
                desc_lower = trial.description.lower()
                if 'simufilam' in desc_lower or 'pti' in desc_lower:
                    asset_names.extend([
                        'simufilam', 'PTI-125', 'filamin A inhibitor'
                    ])
            
            # Remove duplicates and empty strings
            asset_names = list(set([name for name in asset_names if name.strip()]))
            
            # Fallback to trial title if no specific drug names found
            if not asset_names and trial.title:
                asset_names = [trial.title]
            
            logger.info(f"Extracted {len(asset_names)} asset names for trial {trial.trial_id}")
            return asset_names
            
        except Exception as e:
            logger.error(f"Error extracting asset names from trial {trial.trial_id}: {e}")
            return [trial.title] if trial.title else []
    
    def _extract_comprehensive_indications(self, trial: Trial) -> List[str]:
        """
        Extract comprehensive indication terms from trial data.
        
        Args:
            trial: Trial object from database
            
        Returns:
            List of comprehensive indication terms and synonyms
        """
        indications = []
        
        try:
            # Extract from trial title
            if trial.title:
                title_lower = trial.title.lower()
                
                # Check for Alzheimer's disease patterns
                if 'alzheimer' in title_lower or 'dementia' in title_lower:
                    indications.extend([
                        'Alzheimer Disease', 'Alzheimer\'s Disease', 'AD',
                        'dementia', 'cognitive impairment', 'mild cognitive impairment',
                        'MCI', 'Alzheimer dementia', 'senile dementia'
                    ])
                
                # Check for other common indications
                if 'parkinson' in title_lower:
                    indications.extend(['Parkinson Disease', 'Parkinson\'s Disease', 'PD'])
                
                if 'cancer' in title_lower or 'tumor' in title_lower or 'oncology' in title_lower:
                    indications.extend(['cancer', 'tumor', 'oncology', 'neoplasm'])
                
                if 'diabetes' in title_lower:
                    indications.extend(['diabetes', 'diabetes mellitus', 'DM'])
            
            # Extract from trial description if available
            if trial.description:
                desc_lower = trial.description.lower()
                if 'alzheimer' in desc_lower:
                    indications.extend(['Alzheimer Disease', 'dementia', 'cognitive impairment'])
            
            # Remove duplicates and empty strings
            indications = list(set([ind for ind in indications if ind.strip()]))
            
            # Fallback to trial title if no specific indications found
            if not indications and trial.title:
                indications = [trial.title]
            
            logger.info(f"Extracted {len(indications)} indication terms for trial {trial.trial_id}")
            return indications
            
        except Exception as e:
            logger.error(f"Error extracting indications from trial {trial.trial_id}: {e}")
            return [trial.title] if trial.title else []
