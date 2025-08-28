"""
Literature Pipeline Implementation.

This module implements the three-stage literature processing pipeline:
- Stage A: Metadata-only discovery
- Stage B: Abstract evaluation and scoring
- Stage C: Full-text on-demand retrieval

The pipeline integrates with:
- LiteratureScorer: U0/U1 utility scoring
- DocumentQueue: Trial priority queue management
- LLMEvaluator: LLM-driven evaluation engine
- SmartPubMedClient: Three-stage retrieval
- BudgetMonitor: Cost tracking and budget control
"""

import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .literature_scoring import LiteratureScorer
from .document_queue import DocumentQueue, DocumentCandidate, TrialStatus
from .llm_evaluator import LLMEvaluator, StopDecision
from .smart_pubmed import SmartPubMedClient

logger = logging.getLogger(__name__)


@dataclass
class PipelineStage:
    """Represents a single stage in the literature pipeline."""
    stage_name: str
    trial_id: str
    start_time: datetime
    success: bool = False
    results: Dict[str, Any] = None
    error_message: Optional[str] = None
    end_time: Optional[datetime] = None
    
    def __post_init__(self):
        if self.results is None:
            self.results = {}
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate stage duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


@dataclass
class PipelineResult:
    """Result of a complete pipeline execution."""
    trial_id: str
    stages: List[PipelineStage]
    overall_success: bool
    total_duration: float
    final_decision: StopDecision
    total_cost: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class LiteraturePipeline:
    """
    Three-stage literature processing pipeline.
    
    This pipeline implements the cost-optimized literature ingestion strategy:
    - Stage A: Cheap metadata search to find candidates
    - Stage B: Moderate abstract evaluation to score utility
    - Stage C: Expensive full-text retrieval only for high-utility documents
    """
    
    def __init__(self, config: Dict[str, Any], db_session=None, run_id=None, execution_id=None,
                 scorer=None, queue=None, evaluator=None, pubmed_client=None, budget_monitor=None):
        """
        Initialize the literature pipeline.
        
        Args:
            config: Configuration dictionary with pipeline parameters
            db_session: Database session for persistence
            run_id: Optional run ID to use for this pipeline execution
            execution_id: Optional execution ID for cost tracking
            scorer: Pre-initialized LiteratureScorer instance
            queue: Pre-initialized DocumentQueue instance
            evaluator: Pre-initialized LLMEvaluator instance
            pubmed_client: Pre-initialized SmartPubMedClient instance
            budget_monitor: Pre-initialized BudgetMonitor instance
        """
        self.db_session = db_session
        self.config = config
        self.run_id = run_id
        self.execution_id = execution_id
        
        # Use pre-initialized components if provided, otherwise create new ones
        if scorer:
            self.scorer = scorer
        else:
            # Extract scoring configuration
            scoring_config_dict = config.get('scoring', {})
            from .literature_scoring import ScoringConfig
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
                tau_abstract=scoring_config_dict.get('tau_abstract', 0.40),
                theta_high=scoring_config_dict.get('theta_high', 0.80),
                theta_low=scoring_config_dict.get('theta_low', 0.20),
                delta_min=scoring_config_dict.get('delta_min', 0.05)
            )
            self.scorer = LiteratureScorer(scoring_config)
        
        if queue:
            self.queue = queue
        else:
            self.queue = DocumentQueue(
                config.get('queue', {})
            )
        
        if evaluator:
            self.evaluator = evaluator
        else:
            # Initialize LLM evaluator with real client
            from .llm_client import create_llm_client
            try:
                llm_client = create_llm_client("openai")
                self.evaluator = LLMEvaluator(
                    config.get('evaluation', {}),
                    llm_client=llm_client
                )
                logger.info("LLM evaluator initialized with OpenAI client")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM client, using mock evaluation: {e}")
                self.evaluator = LLMEvaluator(
                    config.get('evaluation', {})
                )
        
        if pubmed_client:
            self.pubmed_client = pubmed_client
        else:
            # Initialize Smart PubMed client
            self.pubmed_client = SmartPubMedClient(
                config.get('smart_pubmed', {})
            )
        
        if budget_monitor:
            self.budget_monitor = budget_monitor
        else:
            # Initialize budget monitor
            from .budget_monitor import BudgetMonitor
            self.budget_monitor = BudgetMonitor(
                config.get('budget', {}),
                db_session
            )
        
        # Pipeline configuration
        self.enable_stage_c = config.get('enable_stage_c', False)
        self.auto_evaluation = config.get('auto_evaluation', True)
        self.evaluation_interval = config.get('evaluation_interval', 3)
        
        # Statistics
        self.stats = {
            'pipelines_run': 0,
            'trials_processed': 0,
            'documents_discovered': 0,
            'documents_evaluated': 0,
            'full_text_requests': 0,
            'total_processing_time': 0.0,
            'total_cost': 0.0
        }
        
        logger.info("Literature pipeline initialized with config: %s", config)
    
    def _persist_u0_scores(self, trial_id: str, candidates: List[DocumentCandidate]):
        """Persist U0 scores to database for Stage B processing."""
        try:
            from ..db.models import DocumentUtility, Document
            from sqlalchemy.orm import Session
            
            # Get database session from context
            db_session = self.db_session if hasattr(self, 'db_session') else None
            
            if not db_session:
                logger.warning("No database session available for persisting U0 scores")
                return
            
            # Create DocumentUtility records for each candidate
            for candidate in candidates:
                # First, ensure the document exists in the documents table
                doc_id = int(candidate.doc_id) if candidate.doc_id.isdigit() else 0
                
                # Check if document exists, if not create a placeholder
                existing_doc = db_session.query(Document).filter(Document.doc_id == doc_id).first()
                if not existing_doc:
                    # Create placeholder document for PubMed ID
                    placeholder_doc = Document(
                        doc_id=doc_id,
                        source_type='Abstract',  # PubMed abstracts
                        source_url=f"https://pubmed.ncbi.nlm.nih.gov/{doc_id}/",
                        discovered_at=datetime.now(),
                        status='discovered',
                        title=f"PubMed Abstract {doc_id}",
                        pmid=str(doc_id)
                    )
                    db_session.add(placeholder_doc)
                    logger.debug(f"Created placeholder document for PubMed ID {doc_id}")
                
                # Now create the DocumentUtility record
                utility = DocumentUtility(
                    doc_id=doc_id,
                    trial_id=int(trial_id),
                    run_id=getattr(self, 'run_id', f"pipeline_{int(time.time())}"),
                    u0_score=candidate.u0_score,
                    u1_score=None,  # Will be filled in Stage B
                    uncertainty=None,
                    scoring_metadata={
                        'stage': 'stage_a',
                        'source': 'metadata_only',
                        'timestamp': datetime.now().isoformat()
                    }
                )
                db_session.add(utility)
            
            db_session.commit()
            logger.info(f"Persisted {len(candidates)} U0 scores for trial {trial_id}")
            
        except Exception as e:
            logger.error(f"Failed to persist U0 scores for trial {trial_id}: {e}")
            if db_session:
                db_session.rollback()
    
    def _get_candidates_with_u0_scores(self, trial_id: str) -> List[DocumentCandidate]:
        """Get candidates with U0 scores from database for Stage B processing."""
        try:
            from ..db.models import DocumentUtility
            
            # Get database session from context
            db_session = self.db_session if hasattr(self, 'db_session') else None
            
            if not db_session:
                logger.warning("No database session available for getting U0 scores")
                return []
            
            # Query DocumentUtility table for U0 scores from current run only
            utilities = db_session.query(DocumentUtility).filter(
                DocumentUtility.trial_id == int(trial_id),
                DocumentUtility.u0_score.isnot(None),
                DocumentUtility.run_id == getattr(self, 'run_id', f"pipeline_{int(time.time())}")
            ).all()
            
            # Convert to DocumentCandidate objects
            candidates = []
            for utility in utilities:
                candidate = DocumentCandidate(
                    doc_id=str(utility.doc_id),
                    trial_id=str(utility.trial_id),
                    source_type='pubmed',
                    u0_score=utility.u0_score,
                    u1_score=utility.u1_score,
                    metadata=utility.scoring_metadata or {}
                )
                candidates.append(candidate)
            
            logger.info(f"Retrieved {len(candidates)} candidates with U0 scores for trial {trial_id}")
            return candidates
            
        except Exception as e:
            logger.error(f"Failed to get candidates with U0 scores for trial {trial_id}: {e}")
            return []
    
    def run_pipeline(self, trial_id: str, drug_synonyms: List[str],
                    disease: Optional[str] = None,
                    catalyst_year: Optional[int] = None) -> PipelineResult:
        """
        Run the complete three-stage pipeline for a trial.
        
        Args:
            trial_id: Trial identifier
            drug_synonyms: List of drug names/codes
            disease: Optional disease/indication
            catalyst_year: Year of catalyst event
            
        Returns:
            PipelineResult with complete execution details
        """
        start_time = datetime.now()
        logger.info(f"Starting literature pipeline for trial {trial_id} with run_id {getattr(self, 'run_id', 'unknown')}")
        
        stages = []
        overall_success = True
        final_decision = StopDecision.CONTINUE
        
        try:
            # Stage A: Metadata-only discovery
            stage_a = self._run_stage_a(trial_id, drug_synonyms, disease, catalyst_year)
            stages.append(stage_a)
            
            if not stage_a.success:
                overall_success = False
                logger.error(f"Stage A failed for trial {trial_id}")
                return PipelineResult(
                    trial_id=trial_id,
                    stages=stages,
                    overall_success=False,
                    total_duration=(datetime.now() - start_time).total_seconds(),
                    final_decision=StopDecision.CONTINUE
                )
            
            # Stage B: Abstract evaluation
            stage_b = self._run_stage_b(trial_id)
            stages.append(stage_b)
            
            if not stage_b.success:
                overall_success = False
                logger.error(f"Stage B failed for trial {trial_id}")
            
            # Stage C: Full-text on demand (if enabled and needed)
            if self.enable_stage_c and stage_b.success:
                stage_c = self._run_stage_c(trial_id)
                if stage_c:
                    stages.append(stage_c)
                    if not stage_c.success:
                        overall_success = False
            
            # Run LLM evaluation if enabled
            if self.auto_evaluation and stage_b.success:
                evaluation_result = self._run_llm_evaluation(trial_id)
                if evaluation_result:
                    final_decision = evaluation_result.stop_decision
                    
                    # Update trial status based on evaluation
                    self._update_trial_status(trial_id, final_decision)
            
            # Update statistics
            self._update_stats(trial_id, stages, start_time)
            
            # Commit all pending cost records
            if hasattr(self, 'budget_monitor') and self.budget_monitor:
                self.budget_monitor.commit_pending_costs()
            
            # Calculate total cost from all stages
            total_cost = sum(stage.results.get('cost', 0.0) for stage in stages if hasattr(stage, 'results') and stage.results)
            
            total_duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Pipeline completed for trial {trial_id} in {total_duration:.2f}s")
            
            return PipelineResult(
                trial_id=trial_id,
                stages=stages,
                overall_success=overall_success,
                total_duration=total_duration,
                final_decision=final_decision,
                total_cost=total_cost,
                metadata={
                    'drug_synonyms': drug_synonyms,
                    'disease': disease,
                    'catalyst_year': catalyst_year,
                    'documents_discovered': stage_a.results.get('total_found', 0),
                    'documents_evaluated': stage_b.results.get('total_evaluated', 0) if stage_b.success else 0
                }
            )
            
        except Exception as e:
            logger.error(f"Pipeline failed for trial {trial_id}: {e}")
            overall_success = False
            
            # Commit any pending cost records even on failure
            if hasattr(self, 'budget_monitor') and self.budget_monitor:
                self.budget_monitor.commit_pending_costs()
            
            return PipelineResult(
                trial_id=trial_id,
                stages=stages,
                overall_success=False,
                total_duration=(datetime.now() - start_time).total_seconds(),
                final_decision=StopDecision.CONTINUE,
                total_cost=0.0,
                metadata={'error': str(e)}
            )
    
    def _run_stage_a(self, trial_id: str, drug_synonyms: List[str],
                     disease: Optional[str] = None,
                     catalyst_year: Optional[int] = None) -> PipelineStage:
        """
        Run Stage A: Metadata-only discovery.
        
        Args:
            trial_id: Trial identifier
            drug_synonyms: List of drug names/codes
            disease: Optional disease/indication
            catalyst_year: Year of catalyst event
            
        Returns:
            PipelineStage with Stage A results
        """
        stage = PipelineStage(
            stage_name="Stage A: Metadata Discovery",
            trial_id=trial_id,
            start_time=datetime.now()
        )
        
        try:
            logger.info(f"Running Stage A for trial {trial_id}")
            
            # Check budget before proceeding
            if not self.budget_monitor.can_afford_operation('metadata_fetch', trial_id):
                stage.success = False
                stage.error_message = "Budget exceeded for metadata fetch"
                stage.end_time = datetime.now()
                logger.warning(f"Budget exceeded for Stage A in trial {trial_id}")
                return stage
            
            # Use Smart PubMed client for Stage A
            result = self.pubmed_client.stage_a_metadata_only(
                trial_id, drug_synonyms, disease, catalyst_year
            )
            
            # Record costs for metadata operations
            estimated_cost = self.budget_monitor.estimate_operation_cost('metadata_fetch')
            total_cost = estimated_cost * result.total_found
            
            # Record the cost
            self.budget_monitor.record_cost(
                operation_id=f"stage_a_{trial_id}_{getattr(self, 'run_id', 'unknown')}",
                trial_id=trial_id,
                operation_type='metadata_fetch',
                cost=total_cost,
                metadata={'documents_found': result.total_found, 'run_id': getattr(self, 'run_id', 'unknown')},
                execution_id=self.execution_id
            )
            
            # Update statistics
            self.stats['total_cost'] += total_cost
            
            # Store results
            stage.results = {
                'total_found': result.total_found,
                'candidates': len(result.candidates),
                'processing_time': result.processing_time,
                'top_u0_score': max([c.u0_score for c in result.candidates]) if result.candidates else 0.0,
                'cost': total_cost
            }
            
            # Persist U0 scores to database for Stage B to use
            if result.candidates:
                self._persist_u0_scores(trial_id, result.candidates)
            
            stage.success = True
            stage.end_time = datetime.now()
            
            logger.info(f"Stage A completed for trial {trial_id}: {result.total_found} candidates found, cost: ${total_cost:.3f}")
            
        except Exception as e:
            stage.success = False
            stage.error_message = str(e)
            stage.end_time = datetime.now()
            logger.error(f"Stage A failed for trial {trial_id}: {e}")
        
        return stage
    
    def _run_stage_b(self, trial_id: str) -> PipelineStage:
        """
        Run Stage B: Abstract evaluation.
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            PipelineStage with Stage B results
        """
        stage = PipelineStage(
            stage_name="Stage B: Abstract Evaluation",
            trial_id=trial_id,
            start_time=datetime.now()
        )
        
        try:
            logger.info(f"Running Stage B for trial {trial_id}")
            
            # Get candidates with U0 scores from database (persisted in Stage A)
            candidates = self._get_candidates_with_u0_scores(trial_id)
            
            if not candidates:
                logger.info(f"No candidates with U0 scores found for trial {trial_id}")
                stage.results = {
                    'total_evaluated': 0,
                    'promoted_candidates': 0,
                    'parked_candidates': 0,
                    'processing_time': 0.0,
                    'promotion_rate': 0.0,
                    'cost': 0.0
                }
                stage.success = True
                stage.end_time = datetime.now()
                return stage
            
            # Check budget before proceeding
            high_u0_candidates = [
                c for c in candidates 
                if c.u0_score >= self.scorer.config.tau_abstract
            ]
            
            estimated_cost = self.budget_monitor.estimate_operation_cost('abstract_fetch')
            total_estimated_cost = estimated_cost * len(high_u0_candidates)
            
            if not self.budget_monitor.can_afford_operation('abstract_fetch', trial_id):
                stage.success = False
                stage.error_message = "Budget exceeded for abstract fetch"
                stage.end_time = datetime.now()
                logger.warning(f"Budget exceeded for Stage B in trial {trial_id}")
                return stage
            
            # Use Smart PubMed client for Stage B
            result = self.pubmed_client.stage_b_abstract_evaluation(trial_id)
            
            # Record costs for abstract operations
            actual_cost = estimated_cost * result.total_evaluated
            
            # Only record cost if there's an actual cost (avoid zero costs that violate DB constraints)
            if actual_cost > 0:
                self.budget_monitor.record_cost(
                    operation_id=f"stage_b_{trial_id}_{getattr(self, 'run_id', 'unknown')}",
                    trial_id=trial_id,
                    operation_type='abstract_fetch',
                    cost=actual_cost,
                    metadata={'documents_evaluated': result.total_evaluated, 'run_id': getattr(self, 'run_id', 'unknown')},
                    execution_id=self.execution_id
                )
            
            # Update statistics
            self.stats['total_cost'] += actual_cost
            
            # Store results
            stage.results = {
                'total_evaluated': result.total_evaluated,
                'promoted_candidates': len(result.promoted_candidates),
                'parked_candidates': len(result.parked_candidates),
                'processing_time': result.processing_time,
                'promotion_rate': (
                    len(result.promoted_candidates) / result.total_evaluated 
                    if result.total_evaluated > 0 else 0.0
                ),
                'cost': actual_cost
            }
            
            # Store Stage B results in document queue for LLM evaluation
            if hasattr(self.queue, 'update_trial_candidates'):
                # Update candidates with Stage B results (abstracts and U1 scores)
                updated_candidates = []
                
                # Add promoted candidates
                for candidate in result.promoted_candidates:
                    candidate.stage_b_completed = True
                    candidate.stage_b_result = 'promoted'
                    updated_candidates.append(candidate)
                
                # Add parked candidates  
                for candidate in result.parked_candidates:
                    candidate.stage_b_completed = True
                    candidate.stage_b_result = 'parked'
                    updated_candidates.append(candidate)
                
                # Update the queue with Stage B results
                self.queue.update_trial_candidates(trial_id, updated_candidates)
                logger.info(f"Updated document queue with {len(updated_candidates)} Stage B results for trial {trial_id}")
            
            stage.success = True
            stage.end_time = datetime.now()
            
            # Set trial status to READY_FOR_EVALUATION so LLM evaluation can trigger
            if hasattr(self.queue, 'update_trial_status'):
                self.queue.update_trial_status(trial_id, TrialStatus.READY_FOR_EVALUATION)
                logger.info(f"Trial {trial_id} status set to READY_FOR_EVALUATION after Stage B completion")
            
            logger.info(f"Stage B completed for trial {trial_id}: {result.total_evaluated} evaluated, "
                       f"{len(result.promoted_candidates)} promoted, cost: ${actual_cost:.3f}")
            
        except Exception as e:
            stage.success = False
            stage.error_message = str(e)
            stage.end_time = datetime.now()
            logger.error(f"Stage B failed for trial {trial_id}: {e}")
        
        return stage
    
    def _run_stage_c(self, trial_id: str) -> Optional[PipelineStage]:
        """
        Run Stage C: Full-text on-demand retrieval.
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            PipelineStage with Stage C results, or None if not needed
        """
        if not self.enable_stage_c:
            return None
        
        stage = PipelineStage(
            stage_name="Stage C: Full-Text Retrieval",
            trial_id=trial_id,
            start_time=datetime.now()
        )
        
        try:
            logger.info(f"Running Stage C for trial {trial_id}")
            
            # Check if there are high-utility candidates that need full-text
            high_u1_candidates = self.queue.get_high_utility_candidates(trial_id)
            
            if not high_u1_candidates:
                logger.info(f"No high-utility candidates for full-text retrieval in trial {trial_id}")
                stage.results = {
                    'full_text_requests': 0,
                    'documents_retrieved': 0,
                    'processing_time': 0.0,
                    'cost': 0.0
                }
                stage.success = True
                stage.end_time = datetime.now()
                return stage
            
            # Check budget before proceeding
            estimated_cost = self.budget_monitor.estimate_operation_cost('full_text_fetch')
            total_estimated_cost = estimated_cost * len(high_u1_candidates)
            
            if not self.budget_monitor.can_afford_operation('full_text_fetch', trial_id):
                stage.success = False
                stage.error_message = "Budget exceeded for full-text fetch"
                stage.end_time = datetime.now()
                logger.warning(f"Budget exceeded for Stage C in trial {trial_id}")
                return stage
            
            # Simulate full-text retrieval (in real implementation, this would fetch actual documents)
            # For now, we'll just record the request
            actual_cost = estimated_cost * len(high_u1_candidates)
            
            self.budget_monitor.record_cost(
                operation_id=f"stage_c_{trial_id}_{getattr(self, 'run_id', 'unknown')}",
                trial_id=trial_id,
                operation_type='full_text_fetch',
                cost=actual_cost,
                metadata={'full_text_requests': len(high_u1_candidates), 'run_id': getattr(self, 'run_id', 'unknown')},
                execution_id=self.execution_id
            )
            
            # Update statistics
            self.stats['total_cost'] += actual_cost
            self.stats['full_text_requests'] += len(high_u1_candidates)
            
            # Store results
            stage.results = {
                'full_text_requests': len(high_u1_candidates),
                'documents_retrieved': len(high_u1_candidates),
                'processing_time': 0.0,  # Simulated
                'cost': actual_cost
            }
            
            stage.success = True
            stage.end_time = datetime.now()
            
            logger.info(f"Stage C completed for trial {trial_id}: {len(high_u1_candidates)} full-text requests, "
                       f"cost: ${actual_cost:.3f}")
            
        except Exception as e:
            stage.success = False
            stage.error_message = str(e)
            stage.end_time = datetime.now()
            logger.error(f"Stage C failed for trial {trial_id}: {e}")
        
        return stage
    
    def _run_llm_evaluation(self, trial_id: str) -> Optional[Any]:
        """
        Run LLM evaluation for trial-level decisions.
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            Evaluation result with stop decision, or None if not needed
        """
        try:
            logger.info(f"Running LLM evaluation for trial {trial_id}")
            
            # Get trial status and recent evaluations
            trial_status = self.queue.get_trial_status(trial_id)
            
            if not trial_status or trial_status != TrialStatus.READY_FOR_EVALUATION:
                logger.info(f"Trial {trial_id} not ready for LLM evaluation")
                return None
            
            # Check budget before proceeding
            if not self.budget_monitor.can_afford_operation('llm_evaluation', trial_id):
                logger.warning(f"Budget exceeded for LLM evaluation in trial {trial_id}")
                return None
            
            # Get candidates for evaluation
            candidates = self.queue.get_trial_candidates(trial_id)
            logger.info(f"🔍 PIPELINE LLM EVAL: Retrieved {len(candidates)} candidates for trial {trial_id}")
            
            if not candidates:
                logger.warning(f"🔍 PIPELINE LLM EVAL: No candidates found for trial {trial_id}")
                return None
            
            # Log candidate details
            for i, candidate in enumerate(candidates[:3]):  # Log first 3 candidates
                logger.info(f"🔍 PIPELINE LLM EVAL: Candidate {i+1}: doc_id={candidate.doc_id}, u0={candidate.u0_score}, u1={getattr(candidate, 'u1_score', 'N/A')}")
            
            # Run evaluation
            logger.info(f"🔍 PIPELINE LLM EVAL: Calling LLM evaluator with {len(candidates)} candidates")
            result = self.evaluator.evaluate_trial_batch(trial_id, candidates)
            logger.info(f"🔍 PIPELINE LLM EVAL: LLM evaluation result: {result}")
            
            # Record costs for LLM evaluation
            estimated_cost = self.budget_monitor.estimate_operation_cost('llm_evaluation')
            
            self.budget_monitor.record_cost(
                operation_id=f"llm_eval_{trial_id}_{getattr(self, 'run_id', 'unknown')}",
                trial_id=trial_id,
                operation_type='llm_evaluation',
                cost=estimated_cost,
                metadata={'evaluation_type': 'trial_batch', 'run_id': getattr(self, 'run_id', 'unknown')},
                execution_id=self.execution_id
            )
            
            # Update statistics
            self.stats['total_cost'] += estimated_cost
            
            logger.info(f"LLM evaluation completed for trial {trial_id}: {result.stop_decision if result else 'None'}")
            return result
            
        except Exception as e:
            logger.error(f"LLM evaluation failed for trial {trial_id}: {e}")
            return None
    
    def _update_trial_status(self, trial_id: str, decision: StopDecision) -> None:
        """
        Update trial status based on evaluation decision.
        
        Args:
            trial_id: Trial identifier
            decision: Stop decision from LLM evaluation
        """
        try:
            if decision == StopDecision.STOP:
                self.queue.update_trial_status(trial_id, TrialStatus.STOPPED)
            elif decision == StopDecision.PARK:
                self.queue.update_trial_status(trial_id, TrialStatus.PARKED)
            elif decision == StopDecision.PROMOTE:
                self.queue.update_trial_status(trial_id, TrialStatus.PROMOTED)
            else:
                # CONTINUE or REQUEST_FULL_TEXT - keep current status
                pass
            
            logger.info(f"Updated trial {trial_id} status based on decision: {decision}")
            
        except Exception as e:
            logger.error(f"Failed to update trial status for {trial_id}: {e}")
    
    def _update_stats(self, trial_id: str, stages: List[PipelineStage], start_time: datetime) -> None:
        """
        Update pipeline statistics.
        
        Args:
            trial_id: Trial identifier
            stages: List of pipeline stages
            start_time: Pipeline start time
        """
        try:
            self.stats['pipelines_run'] += 1
            self.stats['trials_processed'] += 1
            
            # Count documents discovered and evaluated
            for stage in stages:
                if stage.stage_name == "Stage A: Metadata Discovery" and stage.success:
                    self.stats['documents_discovered'] += stage.results.get('total_found', 0)
                
                elif stage.stage_name == "Stage B: Abstract Evaluation" and stage.success:
                    self.stats['documents_evaluated'] += stage.results.get('total_evaluated', 0)
                
                elif stage.stage_name == "Stage C: Full-Text Retrieval" and stage.success:
                    self.stats['full_text_requests'] += stage.results.get('full_text_requests', 0)
            
            # Update total processing time
            total_duration = (datetime.now() - start_time).total_seconds()
            self.stats['total_processing_time'] += total_duration
            
        except Exception as e:
            logger.error(f"Failed to update stats for trial {trial_id}: {e}")
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """
        Get pipeline statistics.
        
        Returns:
            Dictionary with pipeline statistics
        """
        return {
            **self.stats,
            'avg_processing_time': (
                self.stats['total_processing_time'] / max(1, self.stats['pipelines_run'])
            ),
            'success_rate': (
                self.stats['pipelines_run'] / max(1, self.stats['trials_processed'])
            ),
            'avg_cost_per_trial': (
                self.stats['total_cost'] / max(1, self.stats['trials_processed'])
            ),
            'queue_stats': self.queue.get_queue_stats(),
            'evaluation_stats': self.evaluator.get_evaluation_stats(),
            'budget_stats': self.budget_monitor.get_cost_statistics()
        }
    
    def get_trial_pipeline_history(self, trial_id: str) -> List[PipelineResult]:
        """
        Get pipeline history for a specific trial.
        
        Args:
            trial_id: Trial identifier
            
        Returns:
            List of pipeline results for the trial
        """
        # This would typically query a database
        # For now, return empty list
        return []
    
    def run_batch_pipeline(self, trials: List[Dict[str, Any]]) -> List[PipelineResult]:
        """
        Run pipeline for multiple trials in batch.
        
        Args:
            trials: List of trial configurations
            
        Returns:
            List of pipeline results
        """
        results = []
        
        for trial_config in trials:
            try:
                result = self.run_pipeline(
                    trial_id=trial_config['trial_id'],
                    drug_synonyms=trial_config['drug_synonyms'],
                    disease=trial_config.get('disease'),
                    catalyst_year=trial_config.get('catalyst_year')
                )
                results.append(result)
                
                # Rate limiting between trials
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Failed to run pipeline for trial {trial_config.get('trial_id', 'unknown')}: {e}")
                continue
        
        return results
