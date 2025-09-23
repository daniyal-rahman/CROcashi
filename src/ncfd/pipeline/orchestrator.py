"""
Unified Pipeline Orchestrator for CT.gov, SEC filing, and PubMed literature ingestion.

This module provides:
- Coordinated execution of CT.gov, SEC, and PubMed pipelines
- Dependency management and workflow coordination
- Unified monitoring and reporting
- Error handling and recovery
- Company matching and filtering
- Parallel execution capabilities
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import json
from dataclasses import dataclass, field, asdict

# Core pipeline imports
from .ctgov_pipeline import CtgovPipeline, CtgovPipelineOutput
from .sec_pipeline import SecPipeline, SecPipelineOutput
from .study_card_pipeline import StudyCardPipeline, StudyCardPipelineOutput
from .study_card_pipeline_refactored import StudyCardPipelineRefactored, StudyCardPipelineOutput as StudyCardPipelineOutputRefactored
from .pubmed_pipeline import PubMedPipeline, PubMedPipelineOutput
from .asset_resolver import AssetResolver
from .tracking import TrialVersionTracker
# Early stopping imports removed - use early_stopping module directly
from .lit_queue import LiteratureQueue

# USPTO Patent imports
from ..ingest.uspto.patent_client import USPTOPatentClient
from ..ingest.uspto.patent_types import PatentSearchQuery, PatentRecord
from ..ingest.uspto.patent_query_builder import PatentQueryBuilder, PatentResultProcessor, TrialPatentContext

# Task queue imports
from ..ingest.pubmed.queue_service import TaskQueueService

# Database imports
from ..db.session import session_scope
from ..db.models import Trial, TrialVersion, Company, Asset, CompanyAlias

# Entity imports
from ..entities.schema import EntityPack as EntityPackSchema, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, DateRangeInfo
from ..entities.entity_pack_service import EntityPackService

# Utility imports
from ..utils.config_manager import get_config_manager
from ..utils.error_handler import get_pipeline_error_handler, safe_execute

logger = logging.getLogger(__name__)


# EntityPackManager removed - using EntityPackService directly


@dataclass
class OrchestrationOutput:
    """Result of orchestrated pipeline execution."""
    execution_id: str
    start_time: datetime
    end_time: datetime
    total_processing_time: float = field(init=False, default=0.0)
    
    # Pipeline results - using specific result types
    ctgov_result: Optional['CtgovPipelineOutput'] = None
    sec_result: Optional['SecPipelineOutput'] = None
    pubmed_result: Optional['PubMedPipelineOutput'] = None
    study_card_result: Optional['StudyCardPipelineOutputRefactored'] = None
    independent_analysis_result: Optional[Dict[str, Any]] = None
    
    # Overall metrics
    total_trials_processed: int = 0
    total_filings_processed: int = 0
    total_documents_processed: int = 0
    total_changes_detected: int = 0
    total_significant_changes: int = 0
    
    # Company matching results
    trials_matched_to_companies: int = 0
    public_company_trials: int = 0
    
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
            self.total_significant_changes += self.ctgov_result.material_changes
        
        if self.sec_result:
            self.total_filings_processed += self.sec_result.filings_processed
        
        if self.pubmed_result:
            self.total_documents_processed += self.pubmed_result.documents_processed
        
        # Determine overall success
        self.all_pipelines_successful = (
            (self.ctgov_result.success if self.ctgov_result else True) and
            (self.sec_result.success if self.sec_result else True) and
            (self.pubmed_result.success if self.pubmed_result else True) and
            (self.study_card_result.success if self.study_card_result else True) and
            (self.independent_analysis_result.get('success', True) if self.independent_analysis_result else True)
        )


class PipelineOrchestrator:
    """
    Unified orchestrator for CT.gov, SEC filing, and PubMed literature pipelines.
    
    Features:
    - Coordinated pipeline execution
    - Dependency management
    - Unified monitoring and reporting
    - Error handling and recovery
    - Company matching and filtering
    - Parallel execution capabilities
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the unified orchestrator.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize centralized config manager
        self.config_manager = get_config_manager()
        
        # Initialize error handler
        self.error_handler = get_pipeline_error_handler('orchestrator')
        
        # Initialize core pipelines using passed config
        self.ctgov_pipeline = CtgovPipeline(self.config.get('ctgov', {}))
        self.sec_pipeline = SecPipeline(self.config.get('sec', {}))
        # Use refactored study card pipeline with enhanced services
        self.study_card_pipeline = StudyCardPipelineRefactored(self.config.get('study_card', {}))
        
        # Initialize supporting components
        self.asset_resolver = AssetResolver()
        self.trial_tracker = TrialVersionTracker(self.config_manager.get_section('tracking'))
        self.lit_queue = LiteratureQueue(self.config_manager.get_section('lit_queue'))
        # Use EntityPackService directly instead of wrapper
        self.entity_pack_service = EntityPackService()
        
        # Initialize PubMed components
        self.pubmed_pipeline = PubMedPipeline(self.config_manager.get_section('pubmed'))
        
        # Initialize USPTO Patent components
        self.patent_client = USPTOPatentClient(self.config_manager.get_section('uspto'))
        self.patent_query_builder = PatentQueryBuilder(self.config_manager.get_section('uspto'))
        self.patent_result_processor = PatentResultProcessor()
        
        # Initialize task queue service
        self.task_queue_service = TaskQueueService(
            worker_id=self.config_manager.get_value('worker_id', 'orchestrator')
        )
        
        # State management
        self.execution_order = self.config_manager.get_value('execution_order', ['ctgov', 'sec', 'pubmed', 'study_card'])
        self.parallel_execution = self.config_manager.get_value('parallel_execution', True)
        self.dependency_checking = self.config_manager.get_value('dependency_checking', True)
        self.orchestration_state = {}
        self.state_file = Path(self.config_manager.get_value('state_file', 'orchestration_state.json'))
        self.execution_history = []
        
        # Load existing orchestration state
        self._load_orchestration_state()
        
        # Current execution tracking
        self.current_execution: Optional[OrchestrationOutput] = None
        
        self.logger.info("Unified orchestrator initialized successfully")
    
    
    # ============================================================================
    # MAIN PIPELINE EXECUTION METHODS
    # ============================================================================
    
    async def run_full_pipeline(self, force_full_scan: bool = False) -> OrchestrationOutput:
        """
        Run the complete pipeline with all components.
        
        Args:
            force_full_scan: Whether to force a full scan instead of incremental
            
        Returns:
            OrchestrationOutput with execution details
        """
        execution_id = f"pipeline_{int(time.time())}"
        start_time = datetime.now(timezone.utc)
        
        self.logger.info(f"Starting full pipeline execution: {execution_id}")
        
        # Initialize execution result
        self.current_execution = OrchestrationOutput(
            execution_id=execution_id,
            start_time=start_time,
            end_time=start_time  # Will be updated
        )
        
        try:
            # Step 1: Parallel ingestion (CT.gov + SEC)
            self.logger.info("Step 1: Running parallel ingestion")
            ingestion_results = await self.run_parallel_ingestion(force_full_scan)
            
            # Step 2: Company matching
            self.logger.info("Step 2: Running company matching")
            matched_trials = self.run_company_matching()
            
            # Step 3: Filter for public companies
            self.logger.info("Step 3: Filtering for public company trials")
            public_trials = self._filter_public_company_trials(matched_trials)
            
            # Step 4: PubMed processing
            self.logger.info("Step 4: Running PubMed processing")
            pubmed_results = await self.run_pubmed_processing(public_trials)
            
            # Step 5: Patent searches
            self.logger.info("Step 5: Running patent searches")
            patent_results = await self.run_patent_searches(public_trials)
            
            # Step 6: Study card generation
            self.logger.info("Step 6: Running study card generation")
            study_card_results = self.run_study_card_generation(public_trials)
            
            # Step 7: Pattern evaluation and gate firing
            self.logger.info("Step 7: Running pattern evaluation and gate firing")
            signal_results = await self.run_pattern_evaluation(public_trials)
            
            # Step 8: Independent LLM Analysis
            self.logger.info("Step 8: Running independent LLM analysis")
            independent_analysis_results = await self.run_independent_llm_analysis(public_trials)
            
            # Step 9: Update orchestration state
            self.logger.info("Step 9: Updating orchestration state")
            self._update_orchestration_state()
            
            # Finalize execution result
            self.current_execution.end_time = datetime.now(timezone.utc)
            self.current_execution.finalize()
            
            self.logger.info(f"Pipeline execution completed: {execution_id}")
            return self.current_execution
            
        except Exception as e:
            self.logger.error(f"Pipeline execution failed: {e}")
            self.current_execution.end_time = datetime.now(timezone.utc)
            self.current_execution.errors.append(str(e))
            self.current_execution.finalize()
            raise
    
    async def run_parallel_ingestion(self, force_full_scan: bool = False) -> Dict[str, Any]:
        """
        Run CT.gov and SEC ingestion in parallel.
        
        Args:
            force_full_scan: Whether to force a full scan
            
        Returns:
            Dictionary with ingestion results
        """
        self.logger.info("Starting parallel ingestion")
        
        try:
            # Run CT.gov and SEC in parallel
            ctgov_task = asyncio.create_task(
                self._execute_pipeline_with_error_handling(
                    lambda: self._execute_ctgov_pipeline(force_full_scan),
                    "ctgov"
                )
            )
            
            sec_task = asyncio.create_task(
                self._execute_pipeline_with_error_handling(
                    lambda: self._execute_sec_pipeline(force_full_scan),
                    "sec"
                )
            )
            
            # Wait for both to complete
            ctgov_result, sec_result = await asyncio.gather(ctgov_task, sec_task)
            
            # Store results
            if ctgov_result:
                self.current_execution.ctgov_result = ctgov_result
            if sec_result:
                self.current_execution.sec_result = sec_result
            
            self.logger.info("Parallel ingestion completed")
            return {
                'ctgov': ctgov_result,
                'sec': sec_result
            }
            
        except Exception as e:
            self.logger.error(f"Parallel ingestion failed: {e}")
            raise
    
    def run_company_matching(self) -> List[Dict[str, Any]]:
        """
        Match CT.gov trials to SEC companies.
        
        Returns:
            List of trials with company matching information
        """
        self.logger.info("Starting company matching")
        
        try:
            with session_scope() as session:
                # Get recent CT.gov trials
                recent_trials = session.query(Trial).filter(
                    Trial.updated_at >= datetime.now(timezone.utc) - timedelta(days=7)
                ).all()
                
                matched_trials = []
                
                for trial in recent_trials:
                    # Get the latest trial version for raw data
                    latest_version = session.query(TrialVersion).filter(
                        TrialVersion.trial_id == trial.trial_id
                    ).order_by(TrialVersion.captured_at.desc()).first()
                    
                    if not latest_version:
                        continue
                    
                    # Extract drug names from trial data
                    drug_names = self.asset_resolver.extract_drug_names(latest_version.raw_jsonb or {})
                    
                    if not drug_names:
                        continue
                    
                    # Resolve assets for this trial
                    asset_matches = self.asset_resolver.resolve_assets(
                        session, drug_names, trial.sponsor_company_id
                    )
                    
                    # Find companies that own these assets
                    companies = []
                    for asset_match in asset_matches:
                        asset = session.query(Asset).filter(
                            Asset.asset_id == asset_match.asset_id
                        ).first()
                        
                        if asset and asset.owner_company_id:
                            company = session.query(Company).filter(
                                Company.company_id == asset.owner_company_id
                            ).first()
                            if company:
                                companies.append(company)
                    
                    # Enhanced company matching with SEC data
                    enhanced_companies = self._enhance_company_data(companies, session)
                    
                    # Add company information to trial
                    trial_info = {
                        'trial_id': trial.trial_id,
                        'nct_id': trial.nct_id,
                        'trial_data': trial.trial_data,
                        'assets': [asset.__dict__ for asset in assets],
                        'companies': enhanced_companies,
                        'matched_at': datetime.now(timezone.utc),
                        'matching_confidence': self._calculate_matching_confidence(assets, enhanced_companies)
                    }
                    
                    matched_trials.append(trial_info)
                
                self.logger.info(f"Company matching completed: {len(matched_trials)} trials matched")
                return matched_trials
                
        except Exception as e:
            self.logger.error(f"Company matching failed: {e}")
            raise
    
    def _enhance_company_data(self, companies: List[Company], session) -> List[Dict[str, Any]]:
        """
        Enhance company data with basic information.
        
        Args:
            companies: List of Company objects
            session: Database session
            
        Returns:
            List of enhanced company dictionaries
        """
        enhanced_companies = []
        
        for company in companies:
            enhanced_company = {
                'company_id': company.company_id,
                'name': company.name,
                'ticker': company.ticker,
                'is_public': company.is_public,
                'sector': company.sector,
                'industry': company.industry,
                'market_cap': company.market_cap,
                'enhanced_at': datetime.now(timezone.utc)
            }
            
            enhanced_companies.append(enhanced_company)
        
        return enhanced_companies
    
    # Company enhancement methods removed - implement when actually needed
    
    def _calculate_matching_confidence(self, assets: List[Any], companies: List[Dict[str, Any]]) -> float:
        """
        Calculate confidence score for company matching.
        
        Args:
            assets: List of assets
            companies: List of companies
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not assets or not companies:
            return 0.0
        
        # Simple confidence calculation based on number of assets and companies
        asset_count = len(assets)
        company_count = len(companies)
        
        # Higher confidence with more assets and fewer companies (more specific match)
        if company_count == 0:
            return 0.0
        elif company_count == 1:
            return min(1.0, asset_count * 0.3)
        else:
            return min(0.8, asset_count * 0.2 / company_count)
    
    def _filter_public_company_trials(self, matched_trials: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter trials for public companies only.
        
        Args:
            matched_trials: List of trials with company matching
            
        Returns:
            List of trials filtered for public companies
        """
        public_trials = []
        
        for trial in matched_trials:
            companies = trial.get('companies', [])
            
            # Check if any company is public
            has_public_company = any(
                company.get('is_public', False) for company in companies
            )
            
            if has_public_company:
                public_trials.append(trial)
        
        self.logger.info(f"Filtered to {len(public_trials)} public company trials")
        return public_trials
    
    # ============================================================================
    # PUBMED PROCESSING METHODS
    # ============================================================================
    
    async def run_pubmed_processing(self, trial_list: List[Dict[str, Any]]) -> Optional[PubMedPipelineOutput]:
        """
        Run PubMed processing for filtered trial list.
        
        Args:
            trial_list: List of trials to process
            
        Returns:
            PubMedPipelineOutput for PubMed processing
        """
        self.logger.info(f"Starting PubMed processing for {len(trial_list)} trials")
        
        # Initialize current_execution if not already initialized
        if self.current_execution is None:
            execution_id = f"pubmed_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            self.current_execution = OrchestrationOutput(
                execution_id=execution_id,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc)
            )
        
        try:
            # Extract trial IDs and NCT IDs for pipeline
            trial_ids = [trial['trial_id'] for trial in trial_list]
            self.logger.info(f"DEBUG: Processing {len(trial_ids)} trials: {trial_ids}")
            
            # Get NCT IDs and other trial data for better PubMed processing
            nct_ids = [trial.get('nct_id') for trial in trial_list if trial.get('nct_id')]
            trial_phases = [trial.get('trial_data', {}).get('phase') for trial in trial_list]
            company_names = [trial.get('trial_data', {}).get('sponsor') for trial in trial_list]
            
            # Check existing documents if reuse is enabled
            reuse_enabled = self.config.get('pubmed', {}).get('reuse_existing', True)
            if reuse_enabled:
                existing_counts = await self._check_existing_pubmed_documents(trial_list)
                total_existing = sum(existing_counts.values())
                min_required = self.config.get('pubmed', {}).get('min_documents_required', 1)
                
                if total_existing >= min_required * len(trial_list):
                    self.logger.info(f"Found sufficient existing documents ({total_existing}), skipping PubMed retrieval")
                    
                    return PubMedPipelineOutput(
                        success=True,
                        start_time=datetime.now(timezone.utc),
                        end_time=datetime.now(timezone.utc),
                        documents_processed=total_existing,
                        trials_processed=len(trial_list),
                        errors=[],
                        warnings=[f"Reused {total_existing} existing documents"]
                    )
            
            # Get entity packs for all trials
            entity_packs = []
            asset_names = self.config.get('pubmed', {}).get('asset_names', [])
            indications = self.config.get('pubmed', {}).get('indications', [])
            
            for trial_id in trial_ids:
                entity_pack = self.entity_pack_service.create_from_trial(
                    trial_id, 
                    asset_names=asset_names, 
                    indications=indications
                )
                entity_packs.append(entity_pack)
            
            # Delegate to PubMed pipeline with entity packs
            max_results = self.config.get('pubmed', {}).get('max_results', 1000)
            self.logger.info(f"DEBUG: Using max_results={max_results} for PubMed processing")
            
            result = await self.pubmed_pipeline.execute(
                trial_ids=trial_ids,
                asset_names=self.config.get('pubmed', {}).get('asset_names', []),
                indications=self.config.get('pubmed', {}).get('indications', []),
                max_results=max_results,
                trial_nct_ids=nct_ids,
                trial_phases=trial_phases,
                company_names=company_names,
                entity_packs=entity_packs
            )
            
            # Store result
            self.current_execution.pubmed_result = result
            
            self.logger.info(f"PubMed processing completed: {result.documents_processed} documents processed")
            return result
            
        except Exception as e:
            self.logger.error(f"PubMed processing failed: {e}")
            end_time = datetime.now(timezone.utc)
            
            result = PubMedPipelineOutput(
                success=False,
                start_time=datetime.now(timezone.utc),
                end_time=end_time,
                errors=[str(e)]
            )
            
            self.current_execution.pubmed_result = result
            return result
    
    async def _check_existing_pubmed_documents(self, trial_list: List[Dict[str, Any]]) -> Dict[int, int]:
        """Check existing PubMed documents for trials."""
        existing_counts = {}
        
        for trial in trial_list:
            trial_id = trial['trial_id']
            # Use simplified approach with DocumentManager
            from ..ingest.pubmed.document_manager import DocumentManager
            dm = DocumentManager()
            summary = dm.get_trial_literature_summary(trial_id)
            existing_counts[trial_id] = summary['total_documents']
        
        return existing_counts
    
    # ============================================================================
    # STUDY CARD GENERATION METHODS
    # ============================================================================
    
    async def run_study_card_generation(self, trial_list: List[Dict[str, Any]]) -> Optional[StudyCardPipelineOutputRefactored]:
        """
        Run study card generation for filtered trial list.
        
        Args:
            trial_list: List of trials to generate study cards for
            
        Returns:
            StudyCardPipelineOutput for study card generation
        """
        self.logger.info(f"Starting study card generation for {len(trial_list)} trials")
        
        # Initialize current_execution if not already initialized
        if self.current_execution is None:
            execution_id = f"study_card_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            self.current_execution = OrchestrationOutput(
                execution_id=execution_id,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc)
            )
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Process trials in parallel (study card generation is CPU-bound)
            results = []
            for trial in trial_list:
                try:
                    result = await self._generate_study_card_for_trial(trial)
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Study card generation failed for trial {trial.get('trial_id')}: {e}")
                    results.append({
                        'trial_id': trial.get('trial_id'),
                        'success': False,
                        'error': str(e)
                    })
            
            # Count successful results
            successful_results = [r for r in results if r.get('success', False)]
            failed_results = [r for r in results if not r.get('success', False)]
            
            end_time = datetime.now(timezone.utc)
            
            result = StudyCardPipelineOutputRefactored(
                success=len(failed_results) == 0,
                start_time=start_time,
                end_time=end_time,
                trials_processed=len(trial_list),
                study_cards_generated=len(successful_results),
                factsheets_generated=0,  # Will be updated by individual trial processing
                patterns_detected=0,     # Will be updated by individual trial processing
                quotes_extracted=0,      # Will be updated by individual trial processing
                errors=[r.get('error', 'Unknown error') for r in failed_results],
                warnings=[]
            )
            
            # Store result
            self.current_execution.study_card_result = result
            
            self.logger.info(f"Study card generation completed: {len(successful_results)} successful, {len(failed_results)} failed")
            return result
            
        except Exception as e:
            self.logger.error(f"Study card generation failed: {e}")
            end_time = datetime.now(timezone.utc)
            
            result = StudyCardPipelineOutputRefactored(
                success=False,
                start_time=start_time,
                end_time=end_time,
                trials_processed=len(trial_list),
                study_cards_generated=0,
                factsheets_generated=0,
                patterns_detected=0,
                quotes_extracted=0,
                errors=[str(e)],
                warnings=[]
            )
            
            self.current_execution.study_card_result = result
            return result
    
    async def _generate_study_card_for_trial(self, trial: Dict[str, Any]) -> Dict[str, Any]:
        """Generate study card for a single trial."""
        try:
            trial_id = trial['trial_id']
            trial_data = trial.get('trial_data', {})
            
            # Get asset names from config to ensure consistency with PubMed phase
            asset_names = self.config.get('pubmed', {}).get('asset_names', [])
            indications = self.config.get('pubmed', {}).get('indications', [])
            
            self.logger.info(f"Study card generation for trial {trial_id}: using asset_names={asset_names}, indications={indications}")
            
            # Get or create entity pack for this trial using the same asset names as PubMed phase
            entity_pack = self.entity_pack_service.create_from_trial(
                trial_id, 
                asset_names=asset_names, 
                indications=indications
            )
            
            if entity_pack:
                self.logger.info(f"Entity pack created for trial {trial_id}: asset_canonical={entity_pack.asset.canonical}, asset_aliases={entity_pack.asset.aliases}")
            else:
                self.logger.warning(f"Failed to create entity pack for trial {trial_id}")
            
            # Create proper trial context for the retriever
            trial_context = {
                'trial_id': trial_id,
                'nct_id': trial.get('nct_id'),
                'entity_pack': entity_pack,  # Include entity pack
                **trial_data  # Include all trial data
            }
            
            # Generate study card using the refactored study card pipeline
            # The refactored pipeline expects a list of trials with entity packs
            trial_with_entity_pack = {
                'trial_id': trial_id,
                'nct_id': trial.get('nct_id'),
                **trial_data,
                'entity_pack': entity_pack
            }
            study_card_result = await self.study_card_pipeline.execute([trial_with_entity_pack], [entity_pack] if entity_pack else None)
            
            return {
                'trial_id': trial_id,
                'success': study_card_result.success,
                'study_cards_generated': study_card_result.study_cards_generated,
                'factsheets_generated': study_card_result.factsheets_generated,
                'patterns_detected': study_card_result.patterns_detected,
                'generated_at': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            self.logger.error(f"Study card generation failed for trial {trial.get('trial_id')}: {e}")
            raise
    
    # ============================================================================
    # SIGNAL EVALUATION METHODS
    # ============================================================================
    
    async def run_pattern_evaluation(self, trial_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Run pattern-based evaluation for a list of trials using existing pattern detection system.
        
        Args:
            trial_list: List of trial data dictionaries with trial_id, nct_id, is_pivotal
            
        Returns:
            Dictionary with evaluation results
        """
        self.logger.info(f"🎯 ORCHESTRATOR: Starting pattern evaluation for {len(trial_list)} trials")
        
        try:
            start_time = datetime.now(timezone.utc)
            results = {
                'trials_processed': 0,
                'patterns_detected': 0,
                'gates_fired': 0,
                'trial_results': []
            }
            
            # Use existing pattern detection system
            from ..extract.generators import PatternFamilyDetector
            from ..signals.gates import evaluate_all_gates
            
            pattern_detector = PatternFamilyDetector()
            
            for trial_data in trial_list:
                trial_id = trial_data.get('trial_id')
                if not trial_id:
                    continue
                
                try:
                    # Get trial context for pattern detection
                    trial_context = {
                        'trial_id': trial_id,
                        'nct_id': trial_data.get('nct_id'),
                        'trial_data': trial_data.get('trial_data', {})
                    }
                    
                    # For now, we need document text for pattern detection
                    # This is a limitation - pattern detection requires document text
                    # We'll need to get the latest study card or document for this trial
                    doc_text = self._get_trial_document_text(trial_id)
                    
                    if not doc_text:
                        self.logger.warning(f"No document text found for trial {trial_id}, skipping pattern detection")
                        continue
                    
                    # Run pattern detection
                    pattern_data = {
                        "raw_doc_text": doc_text,
                        "doc_id": f"trial_{trial_id}",
                        "trial_context": trial_context
                    }
                    
                    pattern_result = await pattern_detector.process(pattern_data)
                    
                    if not pattern_result.get('success'):
                        self.logger.warning(f"Pattern detection failed for trial {trial_id}: {pattern_result.get('error_message')}")
                        continue
                    
                    pattern_detections = pattern_result.get('pattern_detections', [])
                    
                    # Convert pattern detections to signals for gate evaluation
                    signals = self._convert_patterns_to_signals(pattern_detections)
                    
                    # Evaluate gates using existing system
                    gates = evaluate_all_gates(signals)
                    
                    fired_gates = {gid: gate for gid, gate in gates.items() if gate.fired}
                    
                    # Track results
                    results['trials_processed'] += 1
                    results['patterns_detected'] += len(pattern_detections)
                    results['gates_fired'] += len(fired_gates)
                    results['trial_results'].append({
                        'trial_id': trial_id,
                        'patterns_detected': len(pattern_detections),
                        'gates_fired': len(fired_gates),
                        'success': True
                    })
                    
                except Exception as e:
                    self.logger.error(f"Error processing trial {trial_id}: {e}")
                    results['trial_results'].append({
                        'trial_id': trial_id,
                        'patterns_detected': 0,
                        'gates_fired': 0,
                        'success': False,
                        'error': str(e)
                    })
            
            end_time = datetime.now(timezone.utc)
            processing_time = (end_time - start_time).total_seconds()
            
            self.logger.info(f"🎯 ORCHESTRATOR: Pattern evaluation completed: {results['trials_processed']} trials, {results['patterns_detected']} patterns, {results['gates_fired']} gates in {processing_time:.1f}s")
            
            return results
            
        except Exception as e:
            self.logger.error(f"🎯 ORCHESTRATOR: Pattern evaluation failed: {e}")
            return None
    
    def _get_trial_document_text(self, trial_id: int) -> Optional[str]:
        """Get document text for a trial (from study card or latest document)."""
        try:
            with session_scope() as session:
                # Try to get study card text first - join study_cards -> documents -> document_text
                from sqlalchemy import text
                study_card_query = text("""
                    SELECT COALESCE(dt.fulltext_text, dt.abstract_text) as text_content
                    FROM study_cards sc
                    JOIN documents d ON sc.doc_id = d.doc_id
                    JOIN document_text dt ON d.doc_id = dt.doc_id
                    WHERE d.trial_id = :trial_id 
                    ORDER BY sc.created_at DESC LIMIT 1
                """)
                
                result = session.execute(study_card_query, {'trial_id': trial_id}).fetchone()
                if result and result[0]:
                    return result[0]
                
                # Fallback: get latest document text directly
                doc_query = text("""
                    SELECT COALESCE(dt.fulltext_text, dt.abstract_text) as text_content
                    FROM documents d
                    JOIN document_text dt ON d.doc_id = dt.doc_id
                    WHERE d.trial_id = :trial_id 
                    ORDER BY d.discovered_at DESC LIMIT 1
                """)
                
                result = session.execute(doc_query, {'trial_id': trial_id}).fetchone()
                if result and result[0]:
                    return result[0]
                
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting document text for trial {trial_id}: {e}")
            return None
    
    def _convert_patterns_to_signals(self, pattern_detections: List[Any]) -> Dict[str, Any]:
        """Convert pattern detections to signal format for gate evaluation."""
        from ..signals.primitives import SignalResult
        
        signals = {}
        
        # Convert F1-F9 patterns to S1-S9 signals
        # This is a simplified mapping - in practice, you'd need more sophisticated conversion
        for detection in pattern_detections:
            family_id = detection.family_id
            pattern_id = detection.pattern_id
            
            # Map pattern families to signals
            if family_id == 'F1':  # Endpoint Validity
                signals['S1'] = SignalResult(
                    fired=True,
                    severity="H" if detection.severity.value >= 2 else "M",
                    reason=f"Endpoint validity pattern detected: {detection.rationale}",
                    value=detection.confidence
                )
            elif family_id == 'F2':  # Power & Analysis
                signals['S2'] = SignalResult(
                    fired=True,
                    severity="H" if detection.severity.value >= 2 else "M",
                    reason=f"Power/analysis pattern detected: {detection.rationale}",
                    value=detection.confidence
                )
            # Add more mappings as needed...
        
        return signals

    # ============================================================================
    # PATENT SEARCH METHODS
    # ============================================================================
    
    async def run_patent_searches(self, trial_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Run patent searches for filtered trial list.
        
        Args:
            trial_list: List of trials to search patents for
            
        Returns:
            Dict with patent search results
        """
        self.logger.info(f"Starting patent searches for {len(trial_list)} trials")
        
        start_time = datetime.now(timezone.utc)
        
        try:
            # Process trials in parallel (with rate limiting)
            tasks = []
            for trial in trial_list:
                task = asyncio.create_task(
                    self._search_patents_for_trial(trial)
                )
                tasks.append(task)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successful results
            successful_results = [r for r in results if not isinstance(r, Exception)]
            failed_results = [r for r in results if isinstance(r, Exception)]
            
            end_time = datetime.now(timezone.utc)
            
            result = {
                "success": len(failed_results) == 0,
                "start_time": start_time,
                "end_time": end_time,
                "documents_processed": len(successful_results),
                "documents_failed": len(failed_results),
                "errors": [str(e) for e in failed_results]
            }
            
            self.logger.info(f"Patent searches completed: {len(successful_results)} successful, {len(failed_results)} failed")
            return result
            
        except Exception as e:
            self.logger.error(f"Patent searches failed: {e}")
            end_time = datetime.now(timezone.utc)
            
            result = {
                "success": False,
                "start_time": start_time,
                "end_time": end_time,
                "errors": [str(e)]
            }
            
            return result
    
    async def _search_patents_for_trial(self, trial: Dict[str, Any]) -> Dict[str, Any]:
        """Search patents for a single trial using the patent query builder."""
        try:
            trial_id = trial['trial_id']
            trial_data = trial.get('trial_data', {})
            companies = trial.get('companies', [])
            
            # Create trial context for patent query building
            trial_context = TrialPatentContext(
                trial_id=trial_id,
                title=trial_data.get('title'),
                interventions=trial_data.get('interventions', []),
                conditions=trial_data.get('conditions', []),
                companies=companies
            )
            
            # Build patent search query using the dedicated builder
            search_query = self.patent_query_builder.build_query_from_trial(trial_context)
            
            # Execute patent search using existing client
            patent_results = self.patent_client.search_patents(search_query)
            
            # Process results using the dedicated processor
            result = self.patent_result_processor.process_patent_results(
                patent_results, trial_id, search_query
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Patent search failed for trial {trial.get('trial_id')}: {e}")
            raise
    
    # Patent search query building moved to dedicated PatentQueryBuilder class
    
    # ============================================================================
    # PIPELINE EXECUTION HELPERS
    # ============================================================================
    
    async def _execute_pipeline_with_error_handling(self, pipeline_func, pipeline_name: str):
        """Execute a pipeline function with centralized error handling."""
        try:
            return pipeline_func()
        except Exception as e:
            # Use centralized error handler
            error_result = self.error_handler.handle_pipeline_error(e, pipeline_name)
            
            # Return a proper error result instead of None
            if pipeline_name == "ctgov":
                return CtgovPipelineOutput(
                    success=False,
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                    errors=[error_result.error_message] if error_result.error_message else [str(e)]
                )
            elif pipeline_name == "sec":
                return SecPipelineOutput(
                    success=False,
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                    errors=[error_result.error_message] if error_result.error_message else [str(e)]
                )
            else:
                return None
    
    def _execute_ctgov_pipeline(self, force_full_scan: bool) -> Optional[CtgovPipelineOutput]:
        """Execute CT.gov pipeline."""
        start_time = datetime.now(timezone.utc)
        
        try:
            result = self.ctgov_pipeline.run_daily_ingestion(force_full_scan)
            
            # Debug: Check if result is None
            if result is None:
                self.logger.error("CT.gov pipeline returned None result")
                raise ValueError("CT.gov pipeline returned None result")
            
            end_time = datetime.now(timezone.utc)
            
            return CtgovPipelineOutput(
                success=True,
                start_time=start_time,
                end_time=end_time,
                trials_processed=result.trials_processed,
                trials_updated=result.trials_updated,
                trials_created=result.trials_new,
                changes_detected=result.changes_detected,
                material_changes=result.significant_changes
            )
            
        except Exception as e:
            self.logger.error(f"CT.gov pipeline execution failed: {e}")
            end_time = datetime.now(timezone.utc)
            
            return CtgovPipelineOutput(
                success=False,
                start_time=start_time,
                end_time=end_time,
                errors=[str(e)]
            )
    
    def _execute_sec_pipeline(self, force_full_scan: bool) -> Optional[SecPipelineOutput]:
        """Execute SEC pipeline."""
        start_time = datetime.now(timezone.utc)
        
        try:
            result = self.sec_pipeline.run_daily_scan(force_full_scan)
            
            end_time = datetime.now(timezone.utc)
            
            return SecPipelineOutput(
                success=True,
                start_time=start_time,
                end_time=end_time,
                filings_processed=result.filings_processed,
                filings_created=result.new_filings,
                filings_updated=result.updated_filings,
                filings_failed=result.filings_failed,
                documents_processed=result.filings_successful
            )
            
        except Exception as e:
            self.logger.error(f"SEC pipeline execution failed: {e}")
            end_time = datetime.now(timezone.utc)
            
            return SecPipelineOutput(
                success=False,
                start_time=start_time,
                end_time=end_time,
                errors=[str(e)]
            )
    
    # ============================================================================
    # STATE MANAGEMENT METHODS
    # ============================================================================
    
    def _load_orchestration_state(self) -> Dict[str, Any]:
        """Load orchestration state from file."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    self.orchestration_state = json.load(f)
                    self.logger.info("Loaded orchestration state from file")
            else:
                self.orchestration_state = {}
                self.logger.info("No existing orchestration state found, starting fresh")
        except Exception as e:
            self.logger.warning(f"Failed to load orchestration state: {e}")
            self.orchestration_state = {}
    
    def _update_orchestration_state(self):
        """Update orchestration state file."""
        try:
            if self.current_execution:
                # Update last run times using pipeline result end times
                if self.current_execution.ctgov_result:
                    self.orchestration_state['last_ctgov_run'] = self.current_execution.ctgov_result.end_time.isoformat()
                
                if self.current_execution.sec_result:
                    self.orchestration_state['last_sec_run'] = self.current_execution.sec_result.end_time.isoformat()
                
                if self.current_execution.pubmed_result:
                    self.orchestration_state['last_pubmed_run'] = self.current_execution.pubmed_result.end_time.isoformat()
                
                if self.current_execution.study_card_result:
                    self.orchestration_state['last_study_card_run'] = self.current_execution.study_card_result.end_time.isoformat()
                
                # Update overall state
                self.orchestration_state['last_full_run'] = self.current_execution.end_time.isoformat()
                self.orchestration_state['last_execution_id'] = self.current_execution.execution_id
                self.orchestration_state['last_run_successful'] = self.current_execution.all_pipelines_successful
            
            # Save state to file
            with open(self.state_file, 'w') as f:
                json.dump(self.orchestration_state, f, indent=2, default=str)
            
            self.logger.info("Updated orchestration state")
            
        except Exception as e:
            self.logger.warning(f"Failed to update orchestration state: {e}")
    
    def _check_dependencies(self) -> bool:
        """Check if pipeline dependencies are met."""
        try:
            # Check if CT.gov has run before SEC
            if 'last_ctgov_run' not in self.orchestration_state:
                self.logger.warning("CT.gov has not run yet, SEC may not have complete data")
                return False
            
            # Check if both CT.gov and SEC have run before PubMed
            if 'last_ctgov_run' not in self.orchestration_state or 'last_sec_run' not in self.orchestration_state:
                self.logger.warning("CT.gov and SEC must run before PubMed processing")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Dependency check failed: {e}")
            return False
    
    # ============================================================================
    # MONITORING AND STATUS METHODS
    # ============================================================================
    
    def get_orchestration_status(self) -> Dict[str, Any]:
        """Get current orchestration status."""
        try:
            status = {
                'orchestrator_initialized': True,
                'current_execution': None,
                'last_full_run': self.orchestration_state.get('last_full_run'),
                'last_run_successful': self.orchestration_state.get('last_run_successful'),
                'pipeline_status': {
                    'ctgov': self._get_pipeline_status('ctgov'),
                    'sec': self._get_pipeline_status('sec'),
                    'pubmed': self._get_pipeline_status('pubmed'),
                    'study_card': self._get_pipeline_status('study_card')
                },
                'execution_history_count': len(self.execution_history)
            }
            
            if self.current_execution:
                status['current_execution'] = {
                    'execution_id': self.current_execution.execution_id,
                    'start_time': self.current_execution.start_time.isoformat(),
                    'status': 'running'
                }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Failed to get orchestration status: {e}")
            return {'error': str(e)}
    
    def _get_last_successful_run(self) -> Optional[str]:
        """Get the last successful run timestamp."""
        return self.orchestration_state.get('last_full_run')
    
    def _get_pipeline_status(self, pipeline_name: str) -> Dict[str, Any]:
        """Get status for a specific pipeline."""
        last_run_key = f'last_{pipeline_name}_run'
        last_run = self.orchestration_state.get(last_run_key)
        
        return {
            'last_run': last_run,
            'has_run': last_run is not None,
            'status': 'unknown'
        }
    
    def get_execution_history(self, limit: Optional[int] = None) -> List[OrchestrationOutput]:
        """Get execution history."""
        if limit:
            return self.execution_history[-limit:]
        return self.execution_history
    
    def clear_execution_history(self, keep_last: int = 10):
        """Clear old execution history, keeping the last N executions."""
        if len(self.execution_history) > keep_last:
            self.execution_history = self.execution_history[-keep_last:]
            self.logger.info(f"Cleared execution history, kept last {keep_last} executions")
    
    # Backfill methods removed - implement when actually needed
    
    # ============================================================================
    # INDEPENDENT LLM ANALYSIS METHODS
    # ============================================================================
    
    async def run_independent_llm_analysis(self, trial_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Run independent LLM analysis for filtered trial list.
        
        Args:
            trial_list: List of trials to analyze
            
        Returns:
            Analysis results for independent LLM analysis
        """
        self.logger.info(f"Starting independent LLM analysis for {len(trial_list)} trials")
        
        # Initialize current_execution if not already initialized
        if self.current_execution is None:
            execution_id = f"independent_analysis_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            self.current_execution = OrchestrationOutput(
                execution_id=execution_id,
                start_time=datetime.now(timezone.utc),
                end_time=datetime.now(timezone.utc)
            )
        
        start_time = datetime.now(timezone.utc)
        
        try:
            from ..synthesis import IndependentLLMAnalysis
            
            # Initialize the independent LLM analysis
            independent_analysis = IndependentLLMAnalysis()
            
            # Process trials in parallel
            results = []
            for trial in trial_list:
                try:
                    result = await self._run_independent_analysis_for_trial(trial, independent_analysis)
                    results.append(result)
                except Exception as e:
                    self.logger.error(f"Independent LLM analysis failed for trial {trial.get('trial_id')}: {e}")
                    results.append({
                        'trial_id': trial.get('trial_id'),
                        'success': False,
                        'error': str(e)
                    })
            
            # Count successful results
            successful_results = [r for r in results if r.get('success', False)]
            failed_results = [r for r in results if not r.get('success', False)]
            
            end_time = datetime.now(timezone.utc)
            
            analysis_summary = {
                'success': len(successful_results) > 0,
                'total_trials': len(trial_list),
                'trials_analyzed': len(trial_list),
                'successful_analyses': len(successful_results),
                'failed_analyses': len(failed_results),
                'start_time': start_time,
                'end_time': end_time,
                'execution_time_seconds': (end_time - start_time).total_seconds(),
                'results': results
            }
            
            # Store result
            self.current_execution.independent_analysis_result = analysis_summary
            
            self.logger.info(f"Independent LLM analysis completed: {len(successful_results)} successful, {len(failed_results)} failed")
            return analysis_summary
            
        except Exception as e:
            self.logger.error(f"Independent LLM analysis failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_trials': len(trial_list),
                'trials_analyzed': 0,
                'successful_analyses': 0,
                'failed_analyses': len(trial_list)
            }
    
    async def _run_independent_analysis_for_trial(self, trial: Dict[str, Any], independent_analysis: 'IndependentLLMAnalysis') -> Dict[str, Any]:
        """Run independent LLM analysis for a single trial."""
        try:
            trial_id = trial['trial_id']
            trial_data = trial.get('trial_data', {})
            
            # Extract trial information
            nct_id = trial.get('nct_id', 'Unknown')
            indication = trial_data.get('indication', 'Unknown')
            phase = trial_data.get('phase', 'Unknown')
            primary_endpoint = trial_data.get('primary_endpoint_text', 'Unknown')
            
            # Run independent LLM analysis
            analysis_result = await independent_analysis.trigger_thinking_analysis(
                trial_id=trial_id,
                nct_id=nct_id,
                indication=indication,
                phase=phase,
                primary_endpoint=primary_endpoint
            )
            
            return {
                'trial_id': trial_id,
                'nct_id': nct_id,
                'success': True,
                'analysis_result': analysis_result,
                'literature_review': analysis_result.get('literature_review', {}),
                'independent_analysis': analysis_result.get('independent_analysis', {}),
                'risk_assessment': analysis_result.get('risk_assessment', 'Unknown'),
                'confidence_score': analysis_result.get('confidence_score', 0.0)
            }
            
        except Exception as e:
            self.logger.error(f"Independent analysis failed for trial {trial.get('trial_id')}: {e}")
            return {
                'trial_id': trial.get('trial_id'),
                'success': False,
                'error': str(e)
            }

