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
from .ctgov_pipeline import CtgovPipeline, CtgovPipelineResult
from .sec_pipeline import SecPipeline, SecPipelineResult
from .study_card_pipeline import StudyCardPipeline, StudyCardPipelineResult
from .pubmed_pipeline import PubMedPipeline, PubMedPipelineResult
from .asset_resolver import AssetResolver
from .tracking import TrialVersionTracker
from .early_stopping import should_stop_early, initialize_top_k_guard, update_top_k_guard
from .lit_queue import LiteratureQueue

# USPTO Patent imports
from ..ingest.uspto.patent_client import USPTOPatentClient
from ..ingest.uspto.patent_types import PatentSearchQuery, PatentRecord

# Task queue imports
from ..ingest.pubmed.queue_service import TaskQueueService

# Database imports
from ..db.session import session_scope
from ..db.models import Trial, TrialVersion, Company, Asset, AssetOwnership

logger = logging.getLogger(__name__)




@dataclass
class OrchestrationResult:
    """Result of orchestrated pipeline execution."""
    execution_id: str
    start_time: datetime
    end_time: datetime
    total_processing_time: float = field(init=False, default=0.0)
    
    # Pipeline results - using specific result types
    ctgov_result: Optional['CtgovPipelineResult'] = None
    sec_result: Optional['SecPipelineResult'] = None
    pubmed_result: Optional['PubMedPipelineResult'] = None
    study_card_result: Optional['StudyCardPipelineResult'] = None
    
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
            (self.study_card_result.success if self.study_card_result else True)
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
        
        # Initialize core pipelines
        self.ctgov_pipeline = CtgovPipeline(config.get('ctgov', {}))
        self.sec_pipeline = SecPipeline(config.get('sec', {}))
        self.study_card_pipeline = StudyCardPipeline(config.get('study_card', {}))
        
        # Initialize supporting components
        self.asset_resolver = AssetResolver()
        self.trial_tracker = TrialVersionTracker(config.get('tracking', {}))
        self.lit_queue = LiteratureQueue(config.get('lit_queue', {}))
        
        # Initialize PubMed components
        self.pubmed_pipeline = PubMedPipeline(config.get('pubmed', {}))
        
        # Initialize USPTO Patent components
        self.patent_client = USPTOPatentClient(config.get('uspto', {}))
        
        # Initialize task queue service
        self.task_queue_service = TaskQueueService(
            worker_id=config.get('worker_id', 'orchestrator')
        )
        
        # State management
        self.execution_order = config.get('execution_order', ['ctgov', 'sec', 'pubmed', 'study_card'])
        self.parallel_execution = config.get('parallel_execution', True)
        self.dependency_checking = config.get('dependency_checking', True)
        self.orchestration_state = {}
        self.state_file = Path(config.get('state_file', 'orchestration_state.json'))
        self.execution_history = []
        
        # Load existing orchestration state
        self._load_orchestration_state()
        
        # Current execution tracking
        self.current_execution: Optional[OrchestrationResult] = None
        
        self.logger.info("Unified orchestrator initialized successfully")
    
    
    # ============================================================================
    # MAIN PIPELINE EXECUTION METHODS
    # ============================================================================
    
    async def run_full_pipeline(self, force_full_scan: bool = False) -> OrchestrationResult:
        """
        Run the complete pipeline with all components.
        
        Args:
            force_full_scan: Whether to force a full scan instead of incremental
            
        Returns:
            OrchestrationResult with execution details
        """
        execution_id = f"pipeline_{int(time.time())}"
        start_time = datetime.now(timezone.utc)
        
        self.logger.info(f"Starting full pipeline execution: {execution_id}")
        
        # Initialize execution result
        self.current_execution = OrchestrationResult(
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
            
            # Step 7: Independent LLM Analysis
            self.logger.info("Step 7: Running independent LLM analysis")
            independent_analysis_results = await self.run_independent_llm_analysis(public_trials)
            
            # Step 8: Update orchestration state
            self.logger.info("Step 7: Updating orchestration state")
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
                        ownerships = session.query(AssetOwnership).filter(
                            AssetOwnership.asset_id == asset_match.asset_id
                        ).all()
                        
                        for ownership in ownerships:
                            company = session.query(Company).filter(
                                Company.company_id == ownership.company_id
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
        Enhance company data with SEC information.
        
        Args:
            companies: List of Company objects
            session: Database session
            
        Returns:
            List of enhanced company dictionaries
        """
        enhanced_companies = []
        
        for company in companies:
            # Get SEC filings for this company
            sec_filings = self._get_sec_filings_for_company(company.company_id, session)
            
            # Get company financial data
            financial_data = self._get_company_financial_data(company.company_id, session)
            
            # Get company market data
            market_data = self._get_company_market_data(company.company_id, session)
            
            enhanced_company = {
                'company_id': company.company_id,
                'name': company.name,
                'ticker': company.ticker,
                'is_public': company.is_public,
                'sector': company.sector,
                'industry': company.industry,
                'market_cap': company.market_cap,
                'sec_filings': sec_filings,
                'financial_data': financial_data,
                'market_data': market_data,
                'enhanced_at': datetime.now(timezone.utc)
            }
            
            enhanced_companies.append(enhanced_company)
        
        return enhanced_companies
    
    def _get_sec_filings_for_company(self, company_id: int, session) -> List[Dict[str, Any]]:
        """
        Get SEC filings for a company.
        
        Args:
            company_id: Company ID
            session: Database session
            
        Returns:
            List of SEC filing dictionaries
        """
        try:
            # This would integrate with SEC pipeline to get recent filings
            # For now, return placeholder data
            return [
                {
                    'filing_type': '10-K',
                    'filing_date': datetime.now(timezone.utc).isoformat(),
                    'filing_url': f'https://sec.gov/edgar/data/{company_id}/10-K',
                    'status': 'processed'
                }
            ]
        except Exception as e:
            self.logger.warning(f"Failed to get SEC filings for company {company_id}: {e}")
            return []
    
    def _get_company_financial_data(self, company_id: int, session) -> Dict[str, Any]:
        """
        Get financial data for a company.
        
        Args:
            company_id: Company ID
            session: Database session
            
        Returns:
            Financial data dictionary
        """
        try:
            # This would integrate with financial data sources
            # For now, return placeholder data
            return {
                'revenue': None,
                'profit': None,
                'assets': None,
                'liabilities': None,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            self.logger.warning(f"Failed to get financial data for company {company_id}: {e}")
            return {}
    
    def _get_company_market_data(self, company_id: int, session) -> Dict[str, Any]:
        """
        Get market data for a company.
        
        Args:
            company_id: Company ID
            session: Database session
            
        Returns:
            Market data dictionary
        """
        try:
            # This would integrate with market data sources
            # For now, return placeholder data
            return {
                'stock_price': None,
                'market_cap': None,
                'volume': None,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            self.logger.warning(f"Failed to get market data for company {company_id}: {e}")
            return {}
    
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
    
    async def run_pubmed_processing(self, trial_list: List[Dict[str, Any]]) -> Optional[PubMedPipelineResult]:
        """
        Run PubMed processing for filtered trial list.
        
        Args:
            trial_list: List of trials to process
            
        Returns:
            PubMedPipelineResult for PubMed processing
        """
        self.logger.info(f"Starting PubMed processing for {len(trial_list)} trials")
        
        try:
            # Extract trial IDs and NCT IDs for pipeline
            trial_ids = [trial['trial_id'] for trial in trial_list]
            
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
                    
                    return PubMedPipelineResult(
                        success=True,
                        start_time=datetime.now(timezone.utc),
                        end_time=datetime.now(timezone.utc),
                        documents_processed=total_existing,
                        trials_processed=len(trial_list),
                        errors=[],
                        warnings=[f"Reused {total_existing} existing documents"]
                    )
            
            # Delegate to PubMed pipeline with additional context
            result = await self.pubmed_pipeline.execute(
                trial_ids=trial_ids,
                asset_names=self.config.get('pubmed', {}).get('asset_names', []),
                indications=self.config.get('pubmed', {}).get('indications', []),
                trial_nct_ids=nct_ids,
                trial_phases=trial_phases,
                company_names=company_names
            )
            
            # Store result
            self.current_execution.pubmed_result = result
            
            self.logger.info(f"PubMed processing completed: {result.documents_processed} documents processed")
            return result
            
        except Exception as e:
            self.logger.error(f"PubMed processing failed: {e}")
            end_time = datetime.now(timezone.utc)
            
            result = PubMedPipelineResult(
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
            # Use simplified approach with db_service
            counts = self.pubmed_pipeline.db_service.get_document_counts_by_stage(trial_id)
            existing_counts[trial_id] = counts['total']
        
        return existing_counts
    
    # ============================================================================
    # STUDY CARD GENERATION METHODS
    # ============================================================================
    
    async def run_study_card_generation(self, trial_list: List[Dict[str, Any]]) -> Optional[StudyCardPipelineResult]:
        """
        Run study card generation for filtered trial list.
        
        Args:
            trial_list: List of trials to generate study cards for
            
        Returns:
            StudyCardPipelineResult for study card generation
        """
        self.logger.info(f"Starting study card generation for {len(trial_list)} trials")
        
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
            
            result = StudyCardPipelineResult(
                trial_id="multiple",  # Multiple trials processed
                success=len(failed_results) == 0,
                start_time=start_time,
                end_time=end_time
            )
            
            # Store result
            self.current_execution.study_card_result = result
            
            self.logger.info(f"Study card generation completed: {len(successful_results)} successful, {len(failed_results)} failed")
            return result
            
        except Exception as e:
            self.logger.error(f"Study card generation failed: {e}")
            end_time = datetime.now(timezone.utc)
            
            result = StudyCardPipelineResult(
                trial_id="multiple",
                success=False,
                start_time=start_time,
                end_time=end_time
            )
            
            self.current_execution.study_card_result = result
            return result
    
    async def _generate_study_card_for_trial(self, trial: Dict[str, Any]) -> Dict[str, Any]:
        """Generate study card for a single trial."""
        try:
            trial_id = trial['trial_id']
            trial_data = trial.get('trial_data', {})
            
            # Create proper trial context for the retriever
            trial_context = {
                'trial_id': trial_id,
                'nct_id': trial.get('nct_id'),
                **trial_data  # Include all trial data
            }
            
            # Generate study card using the study card pipeline
            study_card_result = await self.study_card_pipeline.execute(trial_id, trial_context)
            
            return {
                'trial_id': trial_id,
                'success': study_card_result.success if hasattr(study_card_result, 'success') else True,
                'study_card_id': getattr(study_card_result, 'study_card_id', None),
                'generated_at': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            self.logger.error(f"Study card generation failed for trial {trial.get('trial_id')}: {e}")
            raise
    
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
        """Search patents for a single trial."""
        try:
            trial_id = trial['trial_id']
            trial_data = trial.get('trial_data', {})
            companies = trial.get('companies', [])
            
            # Build patent search query based on trial data and companies
            search_query = self._build_patent_search_query(trial_data, companies)
            
            # Execute patent search
            patent_results = self.patent_client.search_patents(search_query)
            
            # Process patent results
            processed_patents = []
            for patent in patent_results:
                processed_patents.append({
                    'patent_number': patent.patent_number,
                    'title': patent.title,
                    'abstract': patent.abstract,
                    'inventors': patent.inventors,
                    'assignees': patent.assignees,
                    'grant_date': patent.grant_date.isoformat() if patent.grant_date else None,
                    'application_date': patent.application_date.isoformat() if patent.application_date else None,
                    'cpc_classes': patent.cpc_classes,
                    'patent_status': patent.patent_status,
                    'is_pharmaceutical': patent.is_pharmaceutical
                })
            
            return {
                'trial_id': trial_id,
                'search_query': search_query.to_uspto_query(),
                'patents_found': len(processed_patents),
                'processed_patents': processed_patents,
                'searched_at': datetime.now(timezone.utc)
            }
            
        except Exception as e:
            self.logger.error(f"Patent search failed for trial {trial.get('trial_id')}: {e}")
            raise
    
    def _build_patent_search_query(self, trial_data: Dict[str, Any], companies: List[Dict[str, Any]]) -> PatentSearchQuery:
        """
        Build patent search query based on trial data and companies.
        
        Args:
            trial_data: Trial data for context
            companies: List of companies associated with the trial
            
        Returns:
            PatentSearchQuery object
        """
        # Extract key terms from trial data
        title_keywords = []
        abstract_keywords = []
        
        if 'title' in trial_data:
            title = trial_data['title']
            title_keywords = self._extract_patent_keywords_from_title(title)
        
        if 'interventions' in trial_data:
            interventions = trial_data['interventions']
            for intervention in interventions:
                if 'name' in intervention:
                    title_keywords.append(intervention['name'])
        
        if 'conditions' in trial_data:
            conditions = trial_data['conditions']
            for condition in conditions:
                if 'name' in condition:
                    abstract_keywords.append(condition['name'])
        
        # Get company names for assignee search
        assignees = []
        for company in companies:
            if 'name' in company:
                assignees.append(company['name'])
        
        # Build search query
        query = PatentSearchQuery(
            title_keywords=title_keywords[:5],  # Limit to first 5 keywords
            abstract_keywords=abstract_keywords[:5],  # Limit to first 5 keywords
            assignee=assignees[0] if assignees else None,  # Use first company as primary assignee
            pharmaceutical_only=True,  # Focus on pharmaceutical patents
            max_results=100  # Limit results
        )
        
        return query
    
    def _extract_patent_keywords_from_title(self, title: str) -> List[str]:
        """
        Extract patent-relevant keywords from trial title.
        
        Args:
            title: Trial title
            
        Returns:
            List of patent-relevant keywords
        """
        # Simple extraction - could be enhanced with NLP
        words = title.lower().split()
        
        # Filter out common words and focus on technical terms
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'study', 'trial', 'phase', 'randomized', 'controlled', 'clinical'}
        
        # Focus on technical terms that are likely to appear in patents
        technical_terms = [word for word in words if word not in stop_words and len(word) > 3]
        
        # Take first few technical terms
        return technical_terms[:5]
    
    # ============================================================================
    # PIPELINE EXECUTION HELPERS
    # ============================================================================
    
    async def _execute_pipeline_with_error_handling(self, pipeline_func, pipeline_name: str):
        """Execute a pipeline function with error handling."""
        try:
            return pipeline_func()
        except Exception as e:
            self.logger.error(f"{pipeline_name} pipeline execution failed: {e}")
            return None
    
    def _execute_ctgov_pipeline(self, force_full_scan: bool) -> Optional[CtgovPipelineResult]:
        """Execute CT.gov pipeline."""
        start_time = datetime.now(timezone.utc)
        
        try:
            result = self.ctgov_pipeline.run_daily_ingestion(force_full_scan)
            
            end_time = datetime.now(timezone.utc)
            
            return CtgovPipelineResult(
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
            
            return CtgovPipelineResult(
                success=False,
                start_time=start_time,
                end_time=end_time,
                errors=[str(e)]
            )
    
    def _execute_sec_pipeline(self, force_full_scan: bool) -> Optional[SecPipelineResult]:
        """Execute SEC pipeline."""
        start_time = datetime.now(timezone.utc)
        
        try:
            result = self.sec_pipeline.run_daily_scan(force_full_scan)
            
            end_time = datetime.now(timezone.utc)
            
            return SecPipelineResult(
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
            
            return SecPipelineResult(
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
    
    def get_execution_history(self, limit: Optional[int] = None) -> List[OrchestrationResult]:
        """Get execution history."""
        if limit:
            return self.execution_history[-limit:]
        return self.execution_history
    
    def clear_execution_history(self, keep_last: int = 10):
        """Clear old execution history, keeping the last N executions."""
        if len(self.execution_history) > keep_last:
            self.execution_history = self.execution_history[-keep_last:]
            self.logger.info(f"Cleared execution history, kept last {keep_last} executions")
    
    # ============================================================================
    # BACKFILL METHODS
    # ============================================================================
    
    async def run_backfill(
        self,
        start_date: datetime,
        end_date: datetime,
        pipelines: Optional[List[str]] = None
    ) -> OrchestrationResult:
        """
        Run backfill for specified date range and pipelines.
        
        Args:
            start_date: Start date for backfill
            end_date: End date for backfill
            pipelines: List of pipeline names to backfill (None = all)
            
        Returns:
            OrchestrationResult with backfill details
        """
        execution_id = f"backfill_{int(time.time())}"
        start_time = datetime.now(timezone.utc)
        
        self.logger.info(f"Starting backfill: {execution_id} from {start_date} to {end_date}")
        
        # Initialize execution result
        self.current_execution = OrchestrationResult(
            execution_id=execution_id,
            start_time=start_time,
            end_time=start_time  # Will be updated
        )
        
        try:
            # Determine which pipelines to run
            if pipelines is None:
                pipelines = ['ctgov', 'sec', 'pubmed']
            
            # Execute backfill for each pipeline
            if 'ctgov' in pipelines:
                self.logger.info("Running CT.gov backfill")
                ctgov_result = await self._execute_ctgov_backfill(start_date, end_date)
                self.current_execution.ctgov_result = ctgov_result
            
            if 'sec' in pipelines:
                self.logger.info("Running SEC backfill")
                sec_result = await self._execute_sec_backfill(start_date, end_date)
                self.current_execution.sec_result = sec_result
            
            if 'pubmed' in pipelines:
                self.logger.info("Running PubMed backfill")
                pubmed_result = await self._execute_pubmed_backfill(start_date, end_date)
                self.current_execution.pubmed_result = pubmed_result
            
            # Finalize execution result
            self.current_execution.end_time = datetime.now(timezone.utc)
            self.current_execution.finalize()
            
            self.logger.info(f"Backfill completed: {execution_id}")
            return self.current_execution
            
        except Exception as e:
            self.logger.error(f"Backfill failed: {e}")
            self.current_execution.end_time = datetime.now(timezone.utc)
            self.current_execution.errors.append(str(e))
            self.current_execution.finalize()
            raise
    
    async def _execute_ctgov_backfill(self, start_date: datetime, end_date: datetime) -> Optional[CtgovPipelineResult]:
        """Execute CT.gov backfill."""
        start_time = datetime.now(timezone.utc)
        
        try:
            self.logger.info("Executing CT.gov backfill")
            
            # CT.gov backfill would need to be implemented in the CT.gov pipeline
            # For now, return a placeholder result
            end_time = datetime.now(timezone.utc)
            
            return CtgovPipelineResult(
                success=False,
                start_time=start_time,
                end_time=end_time,
                errors=["CT.gov backfill not yet implemented"]
            )
            
        except Exception as e:
            self.logger.error(f"Error executing CT.gov backfill: {e}")
            end_time = datetime.now(timezone.utc)
            
            return CtgovPipelineResult(
                success=False,
                start_time=start_time,
                end_time=end_time,
                errors=[str(e)]
            )
    
    async def _execute_sec_backfill(self, start_date: datetime, end_date: datetime) -> Optional[SecPipelineResult]:
        """Execute SEC backfill."""
        start_time = datetime.now(timezone.utc)
        
        try:
            self.logger.info("Executing SEC backfill")
            
            # SEC backfill would need to be implemented in the SEC pipeline
            # For now, return a placeholder result
            end_time = datetime.now(timezone.utc)
            
            return SecPipelineResult(
                success=False,
                start_time=start_time,
                end_time=end_time,
                errors=["SEC backfill not yet implemented"]
            )
            
        except Exception as e:
            self.logger.error(f"Error executing SEC backfill: {e}")
            end_time = datetime.now(timezone.utc)
            
            return SecPipelineResult(
                success=False,
                start_time=start_time,
                end_time=end_time,
                errors=[str(e)]
            )
    
    async def _execute_pubmed_backfill(self, start_date: datetime, end_date: datetime) -> Optional[PubMedPipelineResult]:
        """Execute PubMed backfill."""
        start_time = datetime.now(timezone.utc)
        
        try:
            self.logger.info("Executing PubMed backfill")
            
            # Delegate to PubMed pipeline's daily ingestion
            result = await self.pubmed_pipeline.run_daily_ingestion(
                force_full_scan=True,
                max_trials=None
            )
            
            # Return the result directly
            return result
            
        except Exception as e:
            self.logger.error(f"Error executing PubMed backfill: {e}")
            end_time = datetime.now(timezone.utc)
            
            return PubMedPipelineResult(
                success=False,
                start_time=start_time,
                end_time=end_time,
                errors=[str(e)]
            )
    
    # ============================================================================
    # TRACKING, EARLY STOPPING, AND LITERATURE QUEUE METHODS
    # ============================================================================
    
    def track_trial_changes(self, trial_id: str, new_study_card: Dict[str, Any], run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Track changes for a trial and detect material modifications.
        
        Args:
            trial_id: Trial identifier
            new_study_card: New study card data
            run_id: Run identifier for tracking
            
        Returns:
            Change detection result
        """
        try:
            result = self.trial_tracker.track_trial_changes(
                trial_id=trial_id,
                new_study_card=new_study_card,
                run_id=run_id
            )
            
            self.logger.info(f"Trial change tracking completed for {trial_id}: {result.has_changes} changes detected")
            return result
            
        except Exception as e:
            self.logger.error(f"Trial change tracking failed for {trial_id}: {e}")
            raise
    
    def should_stop_early(self, trial: Dict[str, Any], config: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """
        Determine if processing should stop early for a trial.
        
        Args:
            trial: Trial state dictionary
            config: Configuration dictionary with thresholds
            
        Returns:
            Tuple of (decision, reason)
        """
        try:
            return should_stop_early(trial, config)
        except Exception as e:
            self.logger.error(f"Early stopping decision failed: {e}")
            return "continue", "error_in_decision"
    
    def initialize_top_k_guard(self, trial: Dict[str, Any], k: int = 10) -> Dict[str, Any]:
        """
        Initialize Top-K guard for a trial.
        
        Args:
            trial: Trial state dictionary
            k: Number of top documents to examine
            
        Returns:
            Updated trial state with top_k_guard initialized
        """
        try:
            return initialize_top_k_guard(trial, k)
        except Exception as e:
            self.logger.error(f"Top-K guard initialization failed: {e}")
            return trial
    
    def update_top_k_guard(self, trial: Dict[str, Any], document: Dict[str, Any], is_top_k: bool = False) -> Dict[str, Any]:
        """
        Update Top-K guard based on new document.
        
        Args:
            trial: Trial state dictionary
            document: Document being processed
            is_top_k: Whether this document is in the top-K
            
        Returns:
            Updated trial state
        """
        try:
            return update_top_k_guard(trial, document, is_top_k)
        except Exception as e:
            self.logger.error(f"Top-K guard update failed: {e}")
            return trial
    
    def add_trial_to_literature_queue(self, trial: Dict[str, Any]) -> bool:
        """
        Add a trial to the literature queue.
        
        Args:
            trial: Trial state dictionary
            
        Returns:
            True if added successfully, False otherwise
        """
        try:
            return self.lit_queue.add_trial(trial)
        except Exception as e:
            self.logger.error(f"Failed to add trial to literature queue: {e}")
            return False
    
    def get_next_trial_from_queue(self) -> Optional[Dict[str, Any]]:
        """
        Get the next trial from the literature queue.
        
        Returns:
            Next trial item or None if queue is empty
        """
        try:
            queue_item = self.lit_queue.get_next_trial()
            if queue_item:
                return {
                    'trial_id': queue_item.trial_id,
                    'nct_id': queue_item.nct_id,
                    'asset': queue_item.asset,
                    'indication': queue_item.indication,
                    'best_S_Rge2': queue_item.best_S_Rge2,
                    'time_to_catalyst': queue_item.time_to_catalyst,
                    'uncertainty': queue_item.uncertainty,
                    'max_expected_utility': queue_item.max_expected_utility,
                    'priority': queue_item.priority,
                    'status': queue_item.status,
                    'added_at': queue_item.added_at,
                    'last_updated': queue_item.last_updated
                }
            return None
        except Exception as e:
            self.logger.error(f"Failed to get next trial from queue: {e}")
            return None
    
    def update_trial_in_queue(self, trial_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a trial in the literature queue.
        
        Args:
            trial_id: Trial identifier
            updates: Updates to apply
            
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            return self.lit_queue.update_trial(trial_id, updates)
        except Exception as e:
            self.logger.error(f"Failed to update trial in queue: {e}")
            return False
    
    def get_literature_queue_status(self) -> Dict[str, Any]:
        """
        Get literature queue status and statistics.
        
        Returns:
            Queue status information
        """
        try:
            return self.lit_queue.get_queue_status()
        except Exception as e:
            self.logger.error(f"Failed to get literature queue status: {e}")
            return {'error': str(e)}
    
    def reprioritize_literature_queue(self) -> Dict[str, Any]:
        """
        Reprioritize the literature queue based on current state.
        
        Returns:
            Reprioritization results
        """
        try:
            return self.lit_queue.reprioritize_queue()
        except Exception as e:
            self.logger.error(f"Failed to reprioritize literature queue: {e}")
            return {'error': str(e)}
    
    async def run_independent_llm_analysis(self, trial_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Run independent LLM analysis for filtered trial list.
        
        Args:
            trial_list: List of trials to analyze
            
        Returns:
            Analysis results for independent LLM analysis
        """
        self.logger.info(f"Starting independent LLM analysis for {len(trial_list)} trials")
        
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


# Create alias for backward compatibility
UnifiedPipelineOrchestrator = PipelineOrchestrator
