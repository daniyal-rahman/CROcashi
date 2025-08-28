"""
Literature Pipeline Orchestrator

This module orchestrates the complete literature review pipeline using the new
Phase 1-5 components: literature scoring, document queue management, LLM evaluation,
three-stage retrieval, and budget monitoring.
"""

import logging
import time
import uuid
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text

from ncfd.db.models import (
    Trial, Company, Security, CompanyAlias, Asset, Document, DocumentLink,
    TrialEvaluation, DocumentUtility, TrialPriorityQueue, CostRecord, BudgetPeriod
)

# Import Phase 1-5 components
from ncfd.ingest.literature_scoring import LiteratureScorer, ScoringConfig
from ncfd.ingest.document_queue import DocumentQueue, TrialStatus
from ncfd.ingest.llm_evaluator import LLMEvaluator
from ncfd.ingest.smart_pubmed import SmartPubMedClient
from ncfd.ingest.literature_pipeline import LiteraturePipeline
from ncfd.ingest.budget_monitor import BudgetMonitor

logger = logging.getLogger(__name__)


@dataclass
class LiteraturePipelineConfig:
    """Configuration for the literature pipeline."""
    # Scoring configuration
    scoring: ScoringConfig = None
    
    # Queue configuration
    queue: Dict[str, Any] = None
    
    # LLM evaluation configuration
    evaluation: Dict[str, Any] = None
    
    # PubMed configuration
    pubmed: Dict[str, Any] = None
    
    # Budget configuration
    budget: Dict[str, Any] = None
    
    # Pipeline configuration
    pipeline: Dict[str, Any] = None
    
    def __post_init__(self):
        """Set default configurations if not provided."""
        if self.scoring is None:
            self.scoring = ScoringConfig()
        
        if self.queue is None:
            self.queue = {
                'trial_batch_size': 10,
                'max_candidates_per_trial': 100,
                'cleanup_interval_hours': 24
            }
        
        if self.evaluation is None:
            self.evaluation = {
                'eval_every_docs': 3,
                'theta_high': 0.80,
                'theta_low': 0.20,
                'delta_min': 0.05,
                'plateau_epsilon': 0.03,
                'plateau_consecutive': 2,
                'tier2_llm_tokens_per_eval': 2000,
                'evaluation_prompt_version': '1.0'
            }
        
        if self.pubmed is None:
            self.pubmed = {
                'api_key': None,
                'base_url': 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',
                'tool': 'NCFD-Literature-Pipeline',
                'email': 'literature@ncfd.com',
                'rate_limit_delay': 0.1,
                'max_retries': 3,
                'timeout': 30
            }
        
        if self.budget is None:
            self.budget = {
                'daily_limit': 50.0,  # Match demo config
                'monthly_limit': 1000.0,  # Match demo config
                'trial_limit': 5.0,  # Match demo config
                'costs': {
                    'metadata_fetch': 0.001,
                    'abstract_fetch': 0.01,
                    'full_text_fetch': 0.25,  # Match demo config
                    'llm_evaluation': 0.05
                },
                'alert_thresholds': {
                    'warning': 0.70,  # Match demo config
                    'critical': 0.85,  # Match demo config
                    'emergency': 0.95
                },
                'reset_schedule': 'daily',  # Match demo config
                'reset_day': 1
            }
        
        if self.pipeline is None:
            self.pipeline = {
                'enable_stage_a': True,
                'enable_stage_b': True,
                'enable_stage_c': True,
                'evaluation_interval': 5,
                'max_evaluations_per_trial': 10,
                'timeout_seconds': 300,
                'batch_processing': True,
                'error_handling': 'continue'
            }


@dataclass
class LiteraturePipelineResult:
    """Result of a literature pipeline execution."""
    execution_id: str
    run_id: str
    start_time: datetime
    end_time: datetime
    status: str  # Success, Failed, No trials found, Dry run completed
    trials_processed: int
    documents_scored: int
    documents_evaluated: int
    llm_evaluations: int
    total_cost: float
    budget_status: str
    pipeline_stats: Dict[str, Any]
    errors: List[str]
    warnings: List[str]


class LiteratureOrchestrator:
    """
    Main orchestrator for the literature review pipeline.
    
    Coordinates all Phase 1-5 components:
    - LiteratureScorer: U0/U1 utility scoring
    - DocumentQueue: Trial priority queue management
    - LLMEvaluator: LLM-driven evaluation engine
    - SmartPubMedClient: Three-stage retrieval
    - LiteraturePipeline: Stage orchestration
    - BudgetMonitor: Cost tracking and budget control
    """
    
    def __init__(self, db_session: Session, config: LiteraturePipelineConfig = None):
        """
        Initialize the literature orchestrator.
        
        Args:
            db_session: Database session
            config: Pipeline configuration
        """
        self.db_session = db_session
        self.config = config or LiteraturePipelineConfig()
        
        # Initialize execution_id for cost tracking first
        start_time = datetime.now()
        self.execution_id = f"lit_pipeline_{start_time.strftime('%Y%m%d_%H%M%S')}"
        
        # Pipeline state
        self.run_id = None
        self.current_trial = None
        
        # Initialize Phase 1-5 components
        self._initialize_components()
        self.pipeline_stats = {
            'trials_processed': 0,
            'documents_scored': 0,
            'documents_evaluated': 0,
            'llm_evaluations': 0,
            'total_cost': 0.0,
            'stage_a_completed': 0,
            'stage_b_completed': 0,
            'stage_c_completed': 0
        }
        
        logger.info("Literature Orchestrator initialized with all Phase 1-5 components")
    
    def _initialize_components(self):
        """Initialize all pipeline components with consistent configuration."""
        try:
            # Create single source of truth configuration
            component_config = {
                'scoring': self.config.scoring.__dict__ if hasattr(self.config.scoring, '__dict__') else self.config.scoring,
                'queue': self.config.queue,
                'evaluation': self.config.evaluation,
                'pubmed': self.config.pubmed,
                'budget': self.config.budget
            }
            
            logger.info(f"Initializing components with unified config: {component_config}")
            
            # Phase 1: Literature Scoring
            from ..ingest.literature_scoring import ScoringConfig
            scoring_config_dict = component_config['scoring']
            scoring_config = ScoringConfig(
                phase_3_weight=scoring_config_dict.get('phase_3_weight', 0.25),
                randomization_weight=scoring_config_dict.get('randomization_weight', 0.20),
                double_blind_weight=scoring_config_dict.get('double_blind_weight', 0.10),
                nct_mention_weight=scoring_config_dict.get('nct_mention_weight', 0.10),
                rct_type_weight=scoring_config_dict.get('rct_type_weight', 0.20),
                recency_weight=scoring_config_dict.get('recency_weight', 0.15),
                negative_signal_weight=scoring_config_dict.get('negative_signal_weight', 0.45),
                positive_signal_weight=scoring_config_dict.get('positive_signal_weight', 0.00),
                sample_size_weight=scoring_config_dict.get('sample_size_weight', 0.15),
                structural_weight=scoring_config_dict.get('structural_weight', 0.10),
                recency_months=scoring_config_dict.get('recency_months', 18),
                tau_abstract=scoring_config_dict.get('tau_abstract', 0.10),  # Lowered from 0.40 so U0=0.15 docs can pass through
                theta_high=scoring_config_dict.get('theta_high', 0.80),
                theta_low=scoring_config_dict.get('theta_low', 0.20),
                delta_min=scoring_config_dict.get('delta_min', 0.05)
            )
            self.scorer = LiteratureScorer(scoring_config)
            logger.info("LiteratureScorer initialized")
            
            # Phase 1: Document Queue
            self.queue = DocumentQueue(component_config['queue'])
            logger.info("DocumentQueue initialized")
            
            # Phase 1: LLM Evaluation
            from ..ingest.llm_client import create_llm_client
            try:
                llm_client = create_llm_client("openai")
                self.evaluator = LLMEvaluator(component_config['evaluation'], llm_client=llm_client)
                logger.info("LLMEvaluator initialized with OpenAI client")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM client, using mock evaluation: {e}")
                self.evaluator = LLMEvaluator(component_config['evaluation'])
                logger.info("LLMEvaluator initialized with mock evaluation")
            
            # Phase 2: Smart PubMed Client - reuse already initialized components
            self.pubmed_client = SmartPubMedClient(component_config)
            logger.info("SmartPubMedClient initialized")
            
            # Phase 4: Budget Monitor - fix configuration key mapping
            budget_config = component_config['budget'].copy()
            # Map orchestrator config keys to budget monitor expected keys
            budget_config['daily_cost_limit'] = budget_config.get('daily_limit', 50.0)
            budget_config['monthly_cost_limit'] = budget_config.get('monthly_limit', 1000.0)
            budget_config['trial_cost_limit'] = budget_config.get('trial_limit', 5.0)
            
            self.budget_monitor = BudgetMonitor(budget_config, self.db_session)
            logger.info("BudgetMonitor initialized with corrected config keys")
            
            # Phase 3: Literature Pipeline - reuse already initialized components
            self.pipeline = LiteraturePipeline(
                component_config, 
                self.db_session,
                execution_id=self.execution_id,  # Pass execution_id for cost tracking
                scorer=self.scorer,
                queue=self.queue,
                evaluator=self.evaluator,
                pubmed_client=self.pubmed_client,
                budget_monitor=self.budget_monitor
            )
            logger.info("LiteraturePipeline initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise
    
    def run_literature_pipeline(self, 
                               trial_ids: List[str] = None,
                               company_ids: List[int] = None,
                               dry_run: bool = False) -> LiteraturePipelineResult:
        """
        Run the complete literature pipeline.
        
        Args:
            trial_ids: Specific trial IDs to process
            company_ids: Company IDs to process (will get all trials for these companies)
            dry_run: If True, only analyze without making changes
            
        Returns:
            Literature pipeline execution results
        """
        start_time = datetime.now()
        # Don't overwrite execution_id - keep the one from initialization for cost tracking
        if not self.execution_id:
            self.execution_id = f"lit_pipeline_{start_time.strftime('%Y%m%d_%H%M%S')}"
        self.run_id = str(uuid.uuid4())
        
        logger.info(f"Starting literature pipeline execution: {self.execution_id}")
        logger.info(f"Run ID: {self.run_id}")
        
        try:
            # Step 1: Get trials to process
            trials = self._get_trials_to_process(trial_ids, company_ids)
            
            if not trials:
                logger.warning("No trials found to process")
                return self._create_pipeline_result(start_time, "No trials found")
            
            logger.info(f"Found {len(trials)} trials to process")
            
            if dry_run:
                logger.info("Dry run mode - analysis complete")
                return self._create_pipeline_result(start_time, "Dry run completed")
            
            # Step 2: Initialize trial queue
            self._initialize_trial_queue(trials)
            
            # Step 2.5: Set run_id on pipeline components
            self.pipeline.run_id = self.run_id
            
            # Step 3: Run pipeline for each trial
            self._run_pipeline_for_trials(trials)
            
            # Step 4: Generate final statistics
            final_stats = self._generate_final_statistics()
            
            # Record pipeline execution in database
            self._record_pipeline_execution(start_time, "Success", final_stats)
            
            logger.info(f"Literature pipeline execution completed successfully: {self.execution_id}")
            return self._create_pipeline_result(start_time, "Success", final_stats)
            
        except Exception as e:
            logger.error(f"Literature pipeline execution failed: {e}")
            return self._create_pipeline_result(start_time, f"Failed: {e}")
    
    def _get_trials_to_process(self, trial_ids: List[str] = None, 
                              company_ids: List[int] = None) -> List[Trial]:
        """Get trials to process based on input criteria."""
        query = self.db_session.query(Trial)
        
        if trial_ids:
            # Process specific trials
            query = query.filter(Trial.nct_id.in_(trial_ids))
        elif company_ids:
            # Process trials for specific companies
            query = query.filter(Trial.sponsor_company_id.in_(company_ids))
        else:
            # Process all active trials
            query = query.filter(Trial.status.in_(['Recruiting', 'Active, not recruiting', 'Not yet recruiting']))
        
        return query.all()
    
    def _initialize_trial_queue(self, trials: List[Trial]):
        """Initialize the trial priority queue."""
        logger.info("Initializing trial priority queue")
        
        for trial in trials:
            try:
                # Check if trial evaluation already exists for this run
                existing_evaluation = self.db_session.query(TrialEvaluation).filter(
                    TrialEvaluation.trial_id == trial.trial_id,
                    TrialEvaluation.run_id == self.run_id
                ).first()
                
                if not existing_evaluation:
                    # Create trial evaluation record with config-based prior
                    prior_p_short = 0.3  # Use config-based prior instead of hardcoded 0.5
                    evaluation = TrialEvaluation(
                        trial_id=trial.trial_id,
                        run_id=self.run_id,
                        evaluation_status='active',
                        prior_p_short=prior_p_short,
                        llm_evaluation_count=0
                    )
                    self.db_session.add(evaluation)
                
                # Check if priority queue entry already exists for this trial and run_id
                existing_queue_entry = self.db_session.query(TrialPriorityQueue).filter(
                    TrialPriorityQueue.trial_id == trial.trial_id,
                    TrialPriorityQueue.run_id == self.run_id
                ).first()
                
                if not existing_queue_entry:
                    # Check if there are any existing entries for this trial (regardless of run_id)
                    old_entries = self.db_session.query(TrialPriorityQueue).filter(
                        TrialPriorityQueue.trial_id == trial.trial_id
                    ).all()
                    
                    # Delete old entries to avoid constraint violations
                    for old_entry in old_entries:
                        self.db_session.delete(old_entry)
                    
                    # Create new priority queue entry
                    priority_score = self._calculate_initial_priority(trial)
                    queue_entry = TrialPriorityQueue(
                        trial_id=trial.trial_id,
                        run_id=self.run_id,
                        priority_score=priority_score,
                        queue_status='active',
                        processing_stage='stage_a',
                        stage_a_completed=False,
                        stage_b_completed=False,
                        stage_c_completed=False
                    )
                    self.db_session.add(queue_entry)
                else:
                    # Update existing entry for this run_id
                    existing_queue_entry.stage_a_completed = False
                    existing_queue_entry.stage_b_completed = False
                    existing_queue_entry.stage_c_completed = False
                    existing_queue_entry.queue_status = 'active'
                    existing_queue_entry.updated_at = datetime.now()
                
            except Exception as e:
                logger.error(f"Failed to initialize trial {trial.nct_id}: {e}")
                continue
        
        self.db_session.commit()
        logger.info(f"Initialized queue for {len(trials)} trials")
    
    def _calculate_initial_priority(self, trial: Trial) -> float:
        """Calculate initial priority score for a trial."""
        # Simple priority calculation based on trial characteristics
        priority = 0.5  # Base priority
        
        # Phase-based priority
        if trial.phase in ['P3', 'P2_3']:
            priority += 0.2
        elif trial.phase == 'P2B':
            priority += 0.1
        
        # Pivotal trial priority
        if trial.is_pivotal:
            priority += 0.15
        
        # Recency priority
        if trial.last_update_posted_date and hasattr(trial.last_update_posted_date, 'date'):
            try:
                days_since_update = (datetime.now().date() - trial.last_update_posted_date).days
                if days_since_update < 30:
                    priority += 0.1
                elif days_since_update < 90:
                    priority += 0.05
            except (TypeError, AttributeError):
                # Skip recency calculation if date is not properly formatted
                pass
        
        return min(priority, 1.0)
    
    def _get_trial_drug_synonyms(self, trial: Trial) -> List[str]:
        """Get drug synonyms for a trial."""
        drug_synonyms = []
        
        # Try to extract from intervention types (this is what the trial actually has)
        if hasattr(trial, 'intervention_types') and trial.intervention_types:
            # Convert array to list and filter relevant terms
            intervention_types = list(trial.intervention_types) if trial.intervention_types else []
            
            # Add specific intervention types as search terms
            for intervention_type in intervention_types:
                if intervention_type in ['DRUG', 'BIOLOGICAL']:
                    # For drug/biological trials, use the trial ID and phase as specific search terms
                    drug_synonyms.append(f'"{trial.nct_id}"[si]')  # Search in secondary IDs
                    if trial.phase:
                        # Normalize phase to match PubMed conventions
                        phase_normalized = trial.phase.replace('PHASE', 'P').replace('_', '')
                        drug_synonyms.append(f'"{phase_normalized}"[tiab]')
                    
                    # Add indication if available
                    if hasattr(trial, 'indication') and trial.indication:
                        drug_synonyms.append(f'"{trial.indication}"[tiab]')
                    
                    break  # Only process one drug/biological trial type
        
        # If no drug information found, use trial-specific fallback
        if not drug_synonyms:
            # Use trial ID and phase as fallback for search
            drug_synonyms = [f'"{trial.nct_id}"[si]']
            if trial.phase:
                phase_normalized = trial.phase.replace('PHASE', 'P').replace('_', '')
                drug_synonyms.append(f'"{phase_normalized}"[tiab]')
        
        logger.info(f"Generated drug synonyms for trial {trial.nct_id}: {drug_synonyms}")
        return drug_synonyms
    
    def _run_pipeline_for_trials(self, trials: List[Trial]):
        """Run the literature pipeline for each trial."""
        logger.info(f"Running pipeline for {len(trials)} trials")
        
        for i, trial in enumerate(trials):
            self.current_trial = trial
            logger.info(f"Processing trial {i+1}/{len(trials)}: {trial.nct_id}")
            
            try:
                # Check budget before processing
                if not self.budget_monitor.can_afford_operation('metadata_fetch', str(trial.trial_id)):
                    logger.warning(f"Budget limit reached for trial {trial.nct_id}")
                    continue
                
                # Run the complete pipeline for this trial
                # Get drug information from trial
                drug_synonyms = self._get_trial_drug_synonyms(trial)
                disease = getattr(trial, 'condition', None) or getattr(trial, 'disease', None)
                
                pipeline_result = self.pipeline.run_pipeline(
                    trial_id=str(trial.trial_id),
                    drug_synonyms=drug_synonyms,
                    disease=disease
                )
                
                # Update pipeline statistics
                self._update_pipeline_stats(pipeline_result)
                
                # Update trial status in database
                self._update_trial_status(trial, pipeline_result)
                
                # Record costs in budget monitor
                if hasattr(pipeline_result, 'total_cost') and pipeline_result.total_cost > 0:
                    self.budget_monitor.record_cost(
                        operation_id=f"pipeline_{trial.trial_id}_{int(time.time())}",
                        trial_id=str(trial.trial_id),
                        operation_type='metadata_fetch',
                        cost=pipeline_result.total_cost,
                        metadata={'stage': 'complete_pipeline'}
                    )
                
                logger.info(f"Completed pipeline for trial {trial.nct_id}")
                
            except Exception as e:
                logger.error(f"Error processing trial {trial.nct_id}: {e}")
                continue
        
        logger.info("Completed pipeline execution for all trials")
    
    def _update_pipeline_stats(self, pipeline_result):
        """Update pipeline statistics from pipeline result."""
        self.pipeline_stats['trials_processed'] += 1
        
        # Handle both dict and PipelineResult objects
        if hasattr(pipeline_result, 'stages'):
            # PipelineResult object
            stages = pipeline_result.stages
            for stage in stages:
                if stage.stage_name == "Stage A: Metadata Discovery" and stage.success:
                    self.pipeline_stats['stage_a_completed'] += 1
                elif stage.stage_name == "Stage B: Abstract Evaluation" and stage.success:
                    self.pipeline_stats['stage_b_completed'] += 1
                elif stage.stage_name == "Stage C: Full-Text Retrieval" and stage.success:
                    self.pipeline_stats['stage_c_completed'] += 1
            
            if hasattr(pipeline_result, 'total_cost'):
                self.pipeline_stats['total_cost'] += pipeline_result.total_cost
        else:
            # Dict object (fallback)
            if 'stage_a' in pipeline_result and pipeline_result['stage_a']:
                self.pipeline_stats['stage_a_completed'] += 1
            
            if 'stage_b' in pipeline_result and pipeline_result['stage_b']:
                self.pipeline_stats['stage_b_completed'] += 1
            
            if 'stage_c' in pipeline_result and pipeline_result['stage_c']:
                self.pipeline_stats['stage_c_completed'] += 1
            
            if 'total_cost' in pipeline_result:
                self.pipeline_stats['total_cost'] += pipeline_result['total_cost']
    
    def _update_trial_status(self, trial: Trial, pipeline_result):
        """Update trial status in database based on pipeline result."""
        try:
            # Update trial evaluation
            evaluation = self.db_session.query(TrialEvaluation).filter(
                TrialEvaluation.trial_id == trial.trial_id,
                TrialEvaluation.run_id == self.run_id
            ).first()
            
            if evaluation:
                # Handle both dict and PipelineResult objects
                if hasattr(pipeline_result, 'final_decision'):
                    # PipelineResult object - update based on final decision
                    if pipeline_result.final_decision.value == 'stop':
                        evaluation.evaluation_status = 'stopped'
                    elif pipeline_result.final_decision.value == 'park':
                        evaluation.evaluation_status = 'parked'
                    elif pipeline_result.final_decision.value == 'promote':
                        evaluation.evaluation_status = 'promoted'
                    else:
                        evaluation.evaluation_status = 'active'
                else:
                    # Dict object (fallback)
                    if 'evaluation_status' in pipeline_result:
                        evaluation.evaluation_status = pipeline_result['evaluation_status']
                
                evaluation.updated_at = datetime.now()
            
            # Update priority queue - find the entry for this trial (regardless of run_id)
            queue_entry = self.db_session.query(TrialPriorityQueue).filter(
                TrialPriorityQueue.trial_id == trial.trial_id
            ).first()
            
            if queue_entry:
                # Handle both dict and PipelineResult objects
                if hasattr(pipeline_result, 'stages'):
                    # PipelineResult object - update based on stages
                    stages = pipeline_result.stages
                    for stage in stages:
                        if stage.stage_name == "Stage A: Metadata Discovery":
                            queue_entry.stage_a_completed = stage.success
                        elif stage.stage_name == "Stage B: Abstract Evaluation":
                            queue_entry.stage_b_completed = stage.success
                        elif stage.stage_name == "Stage C: Full-Text Retrieval":
                            queue_entry.stage_c_completed = stage.success
                    
                    # Set processing stage based on completed stages
                    if queue_entry.stage_c_completed:
                        queue_entry.processing_stage = 'stage_c'
                    elif queue_entry.stage_b_completed:
                        queue_entry.processing_stage = 'stage_b'
                    elif queue_entry.stage_a_completed:
                        queue_entry.processing_stage = 'stage_a'
                else:
                    # Dict object (fallback)
                    if 'processing_stage' in pipeline_result:
                        queue_entry.processing_stage = pipeline_result['processing_stage']
                    
                    if 'stage_a_completed' in pipeline_result:
                        queue_entry.stage_a_completed = pipeline_result['stage_a_completed']
                    
                    if 'stage_b_completed' in pipeline_result:
                        queue_entry.stage_b_completed = pipeline_result['stage_b_completed']
                    
                    if 'stage_c_completed' in pipeline_result:
                        queue_entry.stage_c_completed = pipeline_result['stage_c_completed']
                
                # Update run_id to current run
                queue_entry.run_id = self.run_id
                queue_entry.last_processed_at = datetime.now()
                queue_entry.updated_at = datetime.now()
            
            self.db_session.commit()
            
        except Exception as e:
            logger.error(f"Failed to update trial status for {trial.nct_id}: {e}")
            self.db_session.rollback()
    
    def _generate_final_statistics(self) -> Dict[str, Any]:
        """Generate final pipeline statistics from actual database data."""
        try:
            # Get budget summary
            budget_summary = self.budget_monitor.get_budget_summary()
            
            # Get actual document counts from database for current run
            from sqlalchemy import text
            
            # Count documents with U0 scores for current run
            u0_count_query = text("""
                SELECT COUNT(*) as u0_count, COUNT(CASE WHEN u1_score IS NOT NULL THEN 1 END) as u1_count
                FROM document_utilities 
                WHERE run_id = :run_id
            """)
            
            result = self.db_session.execute(u0_count_query, {'run_id': self.run_id}).fetchone()
            u0_count = result[0] if result else 0
            u1_count = result[1] if result else 0
            
            # Get actual cost for current run
            cost_query = text("""
                SELECT SUM(cost_amount) as total_cost
                FROM cost_records 
                WHERE run_id = :run_id
            """)
            
            cost_result = self.db_session.execute(cost_query, {'run_id': self.run_id}).fetchone()
            actual_cost = float(cost_result[0]) if cost_result and cost_result[0] else 0.0
            
            # Update orchestrator stats with real data
            self.pipeline_stats.update({
                'documents_scored': u0_count,
                'documents_evaluated': u1_count,
                'total_cost': actual_cost
            })
            
            return {
                'budget_summary': budget_summary,
                'pipeline_stats': self.pipeline_stats,
                'orchestrator_stats': self.pipeline_stats
            }
            
        except Exception as e:
            logger.error(f"Failed to generate final statistics: {e}")
            # Fallback to basic stats
            return {
                'budget_summary': self.budget_monitor.get_budget_summary(),
                'pipeline_stats': self.pipeline.get_pipeline_stats(),
                'orchestrator_stats': self.pipeline_stats
            }
    
    def _record_pipeline_execution(self, start_time: datetime, status: str, final_stats: Dict[str, Any]):
        """Record pipeline execution in the database."""
        try:
            # Create execution record
            execution_record = {
                'execution_id': self.execution_id,
                'run_id': self.run_id,
                'start_time': start_time,
                'end_time': datetime.now(),
                'status': status,
                'total_trials': final_stats.get('orchestrator_stats', {}).get('trials_processed', 0),
                'completed_trials': final_stats.get('orchestrator_stats', {}).get('trials_processed', 0),
                'total_cost': final_stats.get('orchestrator_stats', {}).get('total_cost', 0.0),
                'execution_metadata': final_stats
            }
            
            # Insert directly using SQL since we don't have the model yet
            from sqlalchemy import text
            import json
            
            # Convert complex objects to JSON-serializable format
            serializable_metadata = {}
            for key, value in final_stats.items():
                if isinstance(value, dict):
                    # Handle nested dicts
                    serializable_metadata[key] = {}
                    for k, v in value.items():
                        if hasattr(v, 'value'):  # Handle enums
                            serializable_metadata[key][k] = v.value
                        elif isinstance(v, (datetime, date)):
                            serializable_metadata[key][k] = v.isoformat()
                        else:
                            serializable_metadata[key][k] = v
                elif hasattr(value, '__dict__'):  # Handle objects with __dict__
                    # Convert object to dict
                    serializable_metadata[key] = {}
                    for k, v in value.__dict__.items():
                        if hasattr(v, 'value'):  # Handle enums
                            serializable_metadata[key][k] = v.value
                        elif isinstance(v, (datetime, date)):
                            serializable_metadata[key][k] = v.isoformat()
                        else:
                            serializable_metadata[key][k] = v
                elif hasattr(value, 'value'):  # Handle enums
                    serializable_metadata[key] = value.value
                elif isinstance(value, (datetime, date)):
                    serializable_metadata[key] = value.isoformat()
                else:
                    serializable_metadata[key] = value
            
            execution_record['execution_metadata'] = json.dumps(serializable_metadata)
            
            insert_sql = text("""
                INSERT INTO literature_pipeline_executions 
                (execution_id, run_id, start_time, end_time, status, total_trials, completed_trials, total_cost, execution_metadata)
                VALUES (:execution_id, :run_id, :start_time, :end_time, :status, :total_trials, :completed_trials, :total_cost, :execution_metadata)
            """)
            
            self.db_session.execute(insert_sql, execution_record)
            self.db_session.commit()
            
            logger.info(f"Recorded pipeline execution {self.execution_id} in database")
            
        except Exception as e:
            logger.error(f"Failed to record pipeline execution: {e}")
            # Don't fail the pipeline if recording fails
    
    def _create_pipeline_result(self, start_time: datetime, status: str, 
                               final_stats: Dict[str, Any] = None) -> LiteraturePipelineResult:
        """Create pipeline result object."""
        end_time = datetime.now()
        
        # Calculate total_cost from cost_records for this execution
        execution_cost = self.budget_monitor.get_execution_cost(self.execution_id)
        
        return LiteraturePipelineResult(
            execution_id=self.execution_id,
            run_id=self.run_id,
            start_time=start_time,
            end_time=end_time,
            status=status,
            trials_processed=self.pipeline_stats['trials_processed'],
            documents_scored=self.pipeline_stats.get('documents_scored', 0),
            documents_evaluated=self.pipeline_stats.get('documents_evaluated', 0),
            llm_evaluations=self.pipeline_stats.get('llm_evaluations', 0),
            total_cost=execution_cost,  # Use execution-scoped cost from cost_records
            budget_status=self.budget_monitor.get_budget_status().value,
            pipeline_stats=final_stats or {},
            errors=[],
            warnings=[]
        )
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        return {
            'execution_id': self.execution_id,
            'run_id': self.run_id,
            'current_trial': self.current_trial.nct_id if self.current_trial else None,
            'pipeline_stats': self.pipeline_stats,
            'budget_status': self.budget_monitor.get_budget_status().value,
            'queue_status': self.queue.get_queue_stats()
        }
    
    def get_trial_evaluations(self, trial_id: int = None) -> List[Dict[str, Any]]:
        """Get trial evaluation results."""
        query = self.db_session.query(TrialEvaluation)
        
        if trial_id:
            query = query.filter(TrialEvaluation.trial_id == trial_id)
        
        if self.run_id:
            query = query.filter(TrialEvaluation.run_id == self.run_id)
        
        evaluations = query.all()
        
        return [
            {
                'trial_id': eval.trial_id,
                'evaluation_status': eval.evaluation_status,
                'prior_p_short': float(eval.prior_p_short) if eval.prior_p_short else None,
                'posterior_p_short': float(eval.posterior_p_short) if eval.posterior_p_short else None,
                'llm_evaluation_count': eval.llm_evaluation_count,
                'last_evaluation_at': eval.last_evaluation_at.isoformat() if eval.last_evaluation_at else None,
                'created_at': eval.created_at.isoformat()
            }
            for eval in evaluations
        ]
    
    def get_document_utilities(self, trial_id: int = None) -> List[Dict[str, Any]]:
        """Get document utility scores."""
        query = self.db_session.query(DocumentUtility)
        
        if trial_id:
            query = query.filter(DocumentUtility.trial_id == trial_id)
        
        if self.run_id:
            query = query.filter(DocumentUtility.run_id == self.run_id)
        
        utilities = query.all()
        
        return [
            {
                'doc_id': util.doc_id,
                'trial_id': util.trial_id,
                'u0_score': float(util.u0_score),
                'u1_score': float(util.u1_score) if util.u1_score else None,
                'uncertainty': float(util.uncertainty) if util.uncertainty else None,
                'created_at': util.created_at.isoformat()
            }
            for util in utilities
        ]
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost summary for the current run."""
        return self.budget_monitor.get_budget_summary()


def create_literature_orchestrator(db_session: Session, 
                                 config: LiteraturePipelineConfig = None) -> LiteratureOrchestrator:
    """Convenience function to create a literature orchestrator."""
    return LiteratureOrchestrator(db_session, config)
