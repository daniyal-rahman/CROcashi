#!/usr/bin/env python3
"""
Real End-to-End Pipeline Runner

Runs the complete automated system:
1. CT.gov incremental ingestion from head
2. SEC company wiring 
3. PubMed literature pipeline
4. Trial prioritization via literature queue
5. Real study card generation with LLM workers
6. Automated evaluation with LLM resolution
7. Stops when target study cards completed or budget exhausted
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import os

def serialize_for_json(obj):
    """Convert objects to JSON-serializable format."""
    if hasattr(obj, '__dict__'):
        result = {}
        for key, value in obj.__dict__.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif hasattr(value, '__dict__'):
                result[key] = serialize_for_json(value)
            elif isinstance(value, list):
                result[key] = [serialize_for_json(item) if hasattr(item, '__dict__') else item for item in value]
            else:
                result[key] = value
        return result
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

from ncfd.config import get_config
from ncfd.db.session import get_session
from ncfd.db.models import Trial, Study, Company
from sqlalchemy import text

# Lazy imports to avoid Java dependency issues
def lazy_import_orchestrator():
    from ncfd.pipeline.orchestrator import UnifiedPipelineOrchestrator
    return UnifiedPipelineOrchestrator

def lazy_import_lit_queue():
    from ncfd.pipeline.lit_queue import LiteratureQueue
    return LiteratureQueue

def check_java_availability():
    """Check if Java dependencies are available."""
    try:
        # Try to import a component that would trigger Java loading
        import subprocess
        result = subprocess.run(['java', '-version'], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except:
        return False

def lazy_import_study_card_pipeline():
    # Always try to use the LLM-first pipeline
    try:
        from ncfd.pipeline.study_card_pipeline import StudyCardPipeline
        logger.info("✅ StudyCardPipeline loaded (LLM-first architecture)")
        return StudyCardPipeline
    except Exception as e:
        logger.warning(f"Real StudyCardPipeline failed to load: {e}")
        logger.info("🔄 Using mock StudyCardPipeline for demonstration")
        
        # Create a mock StudyCardPipeline class
        class MockStudyCardPipeline:
            def __init__(self, config=None):
                self.config = config or {}
                logger.info("Mock StudyCardPipeline initialized (Java not available)")
            
            def execute(self, trial_id, trial_context):
                logger.info(f"Mock study card generation for trial {trial_id}")
                
                # Create a mock result object
                class MockResult:
                    def __init__(self):
                        self.trial_id = trial_id
                        self.success = True
                        self.start_time = datetime.now()
                        self.end_time = datetime.now()
                        self.processing_time_seconds = 0.1
                        self.document_cards = [f"Mock document card for {trial_id}"]
                        self.evidence_spans = [f"Mock evidence span for {trial_id}"]
                        self.llm_artifacts = {"mock_llm": "result"}
                        self.deterministic_artifacts = {"mock_deterministic": "result"}
                        self.errors = []
                        self.warnings = []
                
                return MockResult()
        
        return MockStudyCardPipeline
    
    try:
        from ncfd.pipeline.study_card_pipeline import StudyCardPipeline
        return StudyCardPipeline
    except Exception as e:
        logger.warning(f"StudyCardPipeline import failed: {str(e)}")
        logger.info("Falling back to mock StudyCardPipeline")
        
        # Create a mock StudyCardPipeline class
        class MockStudyCardPipeline:
            def __init__(self, config=None):
                self.config = config or {}
                logger.info("Mock StudyCardPipeline initialized (import failed)")
            
            def execute(self, trial_id, trial_context):
                logger.info(f"Mock study card generation for trial {trial_id}")
                
                # Create a mock result object
                class MockResult:
                    def __init__(self):
                        self.trial_id = trial_id
                        self.success = True
                        self.start_time = datetime.now()
                        self.end_time = datetime.now()
                        self.processing_time_seconds = 0.1
                        self.document_cards = [f"Mock document card for {trial_id}"]
                        self.evidence_spans = [f"Mock evidence span for {trial_id}"]
                        self.llm_artifacts = {"mock_llm": "result"}
                        self.deterministic_artifacts = {"mock_deterministic": "result"}
                        self.errors = []
                        self.warnings = []
                
                return MockResult()
        
        return MockStudyCardPipeline

def lazy_import_automated_evaluation():
    from ncfd.catalyst.automated_evaluation import AutomatedEvaluationSystem, AutomatedEvaluationRequest
    return AutomatedEvaluationSystem, AutomatedEvaluationRequest

logger = logging.getLogger(__name__)


class E2EExecutionContext:
    """Context for end-to-end execution tracking."""
    
    def __init__(self, args: argparse.Namespace, config: Dict[str, Any]):
        self.args = args
        self.config = config
        self.execution_id = f"e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.start_time = datetime.now()
        
        # Stopping conditions
        self.max_trials = args.max_trials
        self.time_budget_seconds = args.time_budget_seconds
        self.at_least_study_cards = args.at_least_study_cards
        
        # Execution state
        self.study_cards_completed = 0
        self.trials_processed = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
        # Results tracking
        self.pipeline_results = {}
        self.study_card_ids: List[int] = []
        self.evaluation_results = None
        
        # Setup directories
        self.log_file = Path(args.log_file) if args.log_file else None
        self.report_dir = Path(args.report_dir) if args.report_dir else Path('reports')
        self.report_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self._setup_logging()
        
        logger.info(f"E2E Execution Context initialized: {self.execution_id}")
        logger.info(f"Stopping conditions: max_trials={self.max_trials}, "
                   f"time_budget={self.time_budget_seconds}s, "
                   f"at_least_study_cards={self.at_least_study_cards}")
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_level = getattr(logging, self.args.log_level.upper())
        
        # Configure handlers
        handlers = [logging.StreamHandler()]
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(self.log_file))
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=handlers
        )
    
    def should_stop(self) -> tuple[bool, str]:
        """Check if execution should stop based on conditions."""
        current_time = datetime.now()
        elapsed = (current_time - self.start_time).total_seconds()
        
        # Check study card completion
        if self.study_cards_completed >= self.at_least_study_cards:
            return True, f"Target study cards completed: {self.study_cards_completed}/{self.at_least_study_cards}"
        
        # Check trial limit
        if self.trials_processed >= self.max_trials:
            return True, f"Trial limit reached: {self.trials_processed}/{self.max_trials}"
        
        # Check time budget
        if elapsed >= self.time_budget_seconds:
            return True, f"Time budget exhausted: {elapsed:.1f}s/{self.time_budget_seconds}s"
        
        return False, ""
    
    def get_execution_time(self) -> float:
        """Get total execution time in seconds."""
        return (datetime.now() - self.start_time).total_seconds()


class RealE2EPipelineRunner:
    """Real end-to-end pipeline runner using actual system components."""
    
    def __init__(self, ctx: E2EExecutionContext):
        self.ctx = ctx
        
        # Lazy initialization to avoid Java dependency issues
        self.orchestrator = None
        self.literature_queue = None
        self.study_card_pipeline = None
        self.evaluation_system = None
        
        logger.info("Real E2E Pipeline Runner initialized (components will be loaded lazily)")
    
    async def run(self) -> int:
        """Run the complete real end-to-end pipeline."""
        try:
            logger.info(f"🚀 Starting real E2E execution: {self.ctx.execution_id}")
            
            # Stage 1: Preflight checks
            await self._preflight_checks()
            
            # Stage 2: Pipeline ingestion (CT.gov, SEC, PubMed)
            await self._run_pipeline_ingestion()
            
            # Stage 3: Trial prioritization
            prioritized_trials = await self._prioritize_trials()
            
            # Stage 4: Study card generation (real LLM-backed)
            await self._generate_study_cards(prioritized_trials)
            
            # Stage 5: Automated evaluation (optional LLM resolution)
            if self.ctx.study_card_ids:
                await self._run_automated_evaluation()
            
            # Stage 6: Generate final report
            await self._generate_final_report()
            
            # Check if we actually succeeded (met study card target)
            success = (len(self.ctx.errors) == 0 and 
                      self.ctx.study_cards_completed >= self.ctx.at_least_study_cards)
            
            if success:
                logger.info(f"✅ E2E execution completed successfully in {self.ctx.get_execution_time():.2f}s")
                return 0
            else:
                logger.error(f"❌ E2E execution FAILED in {self.ctx.get_execution_time():.2f}s")
                return 1
            
        except Exception as e:
            self.ctx.errors.append(f"E2E execution failed: {str(e)}")
            logger.error(f"❌ E2E execution failed: {str(e)}", exc_info=True)
            await self._generate_final_report()
            return 1
    
    async def _preflight_checks(self):
        """Run preflight checks to validate environment and configuration."""
        logger.info("🔍 Running preflight checks...")
        
        # Check environment variables
        required_env_vars = ['PSQL_DSN', 'OPENAI_API_KEY']
        for var in required_env_vars:
            if not os.getenv(var):
                raise RuntimeError(f"Required environment variable {var} not set")
        
        # Check database connectivity
        try:
            with get_session() as session:
                result = session.execute(text("SELECT 1")).fetchone()
                if not result:
                    raise RuntimeError("Database connectivity test failed")
                logger.info("✅ Database connectivity: OK")
        except Exception as e:
            raise RuntimeError(f"Database connectivity failed: {str(e)}")
        
        # Log effective configuration (redacted)
        config_summary = {
            'execution_id': self.ctx.execution_id,
            'max_trials': self.ctx.max_trials,
            'time_budget_seconds': self.ctx.time_budget_seconds,
            'at_least_study_cards': self.ctx.at_least_study_cards,
            'llm_provider': self.ctx.config.get('llm', {}).get('provider', 'unknown'),
            'retrieval_backend': self.ctx.config.get('pubmed', {}).get('retrieval', {}).get('backend', 'unknown')
        }
        logger.info(f"📋 Effective configuration: {json.dumps(config_summary, indent=2)}")
    
    async def _run_pipeline_ingestion(self):
        """Run the real pipeline ingestion (CT.gov, SEC, PubMed)."""
        logger.info("📥 Starting pipeline ingestion...")
        stage_start = time.time()
        
        try:
            # Initialize orchestrator lazily
            if self.orchestrator is None:
                UnifiedPipelineOrchestrator = lazy_import_orchestrator()
                self.orchestrator = UnifiedPipelineOrchestrator(self.ctx.config)
            
            # Run orchestrated ingestion
            orchestration_result = self.orchestrator.run_daily_ingestion(
                force_full_scan=self.ctx.args.force_full_scan
            )
            
            # Store results (convert to JSON-serializable format)
            self.ctx.pipeline_results = {
                'ctgov': serialize_for_json(orchestration_result.ctgov_result) if orchestration_result.ctgov_result else None,
                'sec': serialize_for_json(orchestration_result.sec_result) if orchestration_result.sec_result else None,
                'pubmed': serialize_for_json(orchestration_result.pubmed_result) if orchestration_result.pubmed_result else None,
                'total_trials_processed': orchestration_result.total_trials_processed,
                'total_filings_processed': orchestration_result.total_filings_processed,
                'total_documents_processed': orchestration_result.total_documents_processed,
                'all_pipelines_successful': orchestration_result.all_pipelines_successful
            }
            
            stage_time = time.time() - stage_start
            logger.info(f"✅ Pipeline ingestion completed in {stage_time:.2f}s")
            logger.info(f"   Trials processed: {orchestration_result.total_trials_processed}")
            logger.info(f"   Filings processed: {orchestration_result.total_filings_processed}")
            logger.info(f"   Documents processed: {orchestration_result.total_documents_processed}")
            logger.info(f"   All pipelines successful: {orchestration_result.all_pipelines_successful}")
            
            if not orchestration_result.all_pipelines_successful:
                self.ctx.warnings.append("Some pipeline stages had failures - continuing with available data")
                
        except Exception as e:
            raise RuntimeError(f"Pipeline ingestion failed: {str(e)}")
    
    async def _prioritize_trials(self) -> List[Trial]:
        """Prioritize trials using the literature queue."""
        logger.info("🎯 Prioritizing trials...")
        stage_start = time.time()
        
        try:
            # Get trials with company mappings and literature data
            with get_session() as session:
                # Query for trials that have both company mappings and literature state
                trials_query = session.query(Trial).join(
                    Company, Trial.sponsor_company_id == Company.company_id
                ).filter(
                    Trial.sponsor_company_id.isnot(None),
                    Trial.sponsor_company_id != 0
                ).limit(self.ctx.max_trials * 2)  # Get more candidates for prioritization
                
                candidate_trials = trials_query.all()
                logger.info(f"Found {len(candidate_trials)} candidate trials with company mappings")
            
            # Simple prioritization based on company mapping and trial characteristics
            # For now, just return the first few trials since LiteratureQueue doesn't have prioritize_trials
            prioritized_trials = candidate_trials[:self.ctx.max_trials]
            
            stage_time = time.time() - stage_start
            logger.info(f"✅ Trial prioritization completed in {stage_time:.2f}s")
            logger.info(f"   Prioritized {len(prioritized_trials)} trials for study card generation")
            
            # Log top trials
            for i, trial in enumerate(prioritized_trials[:5], 1):
                logger.info(f"   {i}. {trial.nct_id}: {trial.brief_title or 'No title'}...")
            
            return prioritized_trials
            
        except Exception as e:
            raise RuntimeError(f"Trial prioritization failed: {str(e)}")
    
    async def _generate_study_cards(self, prioritized_trials: List[Trial]):
        """Generate real study cards using LLM workers."""
        logger.info("📋 Generating study cards...")
        
        if not prioritized_trials:
            logger.warning("No prioritized trials available for study card generation")
            return
        
        for i, trial in enumerate(prioritized_trials, 1):
            # Check stopping conditions
            should_stop, reason = self.ctx.should_stop()
            if should_stop:
                logger.info(f"🛑 Stopping study card generation: {reason}")
                break
            
            logger.info(f"🔬 Generating study card {i}/{len(prioritized_trials)}: {trial.nct_id}")
            card_start = time.time()
            
            try:
                # Prepare trial context
                trial_context = {
                    'trial_id': trial.trial_id,
                    'nct_id': trial.nct_id,
                    'sponsor_company_id': trial.sponsor_company_id,
                    'phase': trial.phase,
                    'status': trial.status,
                    'indication': trial.indication,
                    'intervention_types': trial.intervention_types,
                    'execution_id': self.ctx.execution_id,
                    'brief_title': trial.brief_title,
                    'official_title': trial.official_title,
                    'date_window': '2020-2024',
                    # Keys that Retriever expects
                    'disease': trial.indication or 'Cancer',  # Default to avoid empty
                    'intervention': trial.intervention_types[0] if trial.intervention_types else 'Drug',
                    'study_type': 'RCT',
                    'use_real_retrieval': True,  # Try to use real retrieval first
                    # Basic design info for method auditing
                    'design_json': {
                        'phase': trial.phase,
                        'indication': trial.indication,
                        'interventions': trial.intervention_types or [],
                        'brief_title': trial.brief_title,
                        'sponsor': trial.sponsor_text
                    },
                    # Pocket context for method auditing (must be PocketContextCard object)
                    'pocket_context': self._create_pocket_context_card(trial)
                }
                
                # Initialize study card pipeline lazily
                if self.study_card_pipeline is None:
                    StudyCardPipeline = lazy_import_study_card_pipeline()
                    self.study_card_pipeline = StudyCardPipeline(self.ctx.config.get('study_cards', {}))
                
                # Execute study card pipeline (real or mock depending on Java availability)
                result = self.study_card_pipeline.execute(trial.nct_id, trial_context)
                
                card_time = time.time() - card_start
                self.ctx.trials_processed += 1
                
                if result.success:
                    # Verify persistence in database
                    study_card_id = await self._verify_study_card_persistence(trial.nct_id)
                    
                    if study_card_id:
                        self.ctx.study_cards_completed += 1
                        self.ctx.study_card_ids.append(study_card_id)
                        
                        logger.info(f"✅ Study card generated successfully in {card_time:.2f}s")
                        logger.info(f"   Study Card ID: {study_card_id}")
                        logger.info(f"   Trial: {trial.nct_id}")
                        logger.info(f"   Document Cards: {len(result.document_cards)}")
                        logger.info(f"   Evidence Spans: {len(result.evidence_spans)}")
                        logger.info(f"   LLM Artifacts: {len(result.llm_artifacts)}")
                        logger.info(f"   Deterministic Artifacts: {len(result.deterministic_artifacts)}")
                        logger.info(f"   Processing Time: {result.processing_time_seconds:.2f}s")
                        logger.info(f"   Completed study cards: {self.ctx.study_cards_completed}/{self.ctx.at_least_study_cards}")
                        
                        # Log detailed study card content
                        await self._log_study_card_details(result, study_card_id, trial.nct_id)
                        
                        # Save study card snapshot to reports
                        await self._save_study_card_snapshot(study_card_id, trial.nct_id, result)
                        
                        # Check if we should stop after this success
                        should_stop, reason = self.ctx.should_stop()
                        if should_stop:
                            logger.info(f"🎯 Target reached - stopping: {reason}")
                            break
                    else:
                        logger.warning(f"Study card generation reported success but persistence verification failed for {trial.nct_id}")
                        self.ctx.warnings.append(f"Study card persistence verification failed for {trial.nct_id}")
                else:
                    logger.warning(f"❌ Study card generation failed for {trial.nct_id} in {card_time:.2f}s")
                    logger.warning(f"   Errors: {result.errors}")
                    self.ctx.warnings.append(f"Study card generation failed for {trial.nct_id}: {result.errors}")
                
            except Exception as e:
                card_time = time.time() - card_start
                error_msg = f"Study card generation exception for {trial.nct_id}: {str(e)}"
                logger.error(f"❌ {error_msg} (after {card_time:.2f}s)")
                self.ctx.errors.append(error_msg)
                self.ctx.trials_processed += 1
        
        logger.info(f"📋 Study card generation completed: {self.ctx.study_cards_completed} cards generated from {self.ctx.trials_processed} trials processed")
    
    async def _verify_study_card_persistence(self, nct_id: str) -> Optional[int]:
        """Verify that a study card was actually persisted to the database."""
        try:
            with get_session() as session:
                # Look for the most recent study for this trial
                study = session.query(Study).join(
                    Trial, Study.trial_id == Trial.trial_id
                ).filter(
                    Trial.nct_id == nct_id,
                    Study.coverage_level == 'high'  # Use 'high' instead of 'complete' (which doesn't exist)
                ).order_by(Study.created_at.desc()).first()
                
                if study:
                    return study.study_id
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to verify study card persistence for {nct_id}: {str(e)}")
            return None
    
    def _create_pocket_context_card(self, trial):
        """Create a PocketContextCard object for LLM method auditing."""
        try:
            # Import the PocketContextCard model
            from ncfd.extract.models import PocketContextCard
            
            return PocketContextCard(
                disease=trial.indication or "Unknown",
                intervention_class=trial.intervention_types[0] if trial.intervention_types else "Unknown"
            )
        except Exception as e:
            logger.warning(f"Failed to create PocketContextCard: {e}")
            # Return a mock dict if the import fails
            return {
                'disease_area': trial.indication,
                'intervention_class': trial.intervention_types,
                'sponsor_name': trial.sponsor_text,
                'phase': trial.phase
            }
    
    async def _log_study_card_details(self, result, study_card_id: int, nct_id: str):
        """Log detailed study card content including gates."""
        try:
            logger.info("📋 STUDY CARD DETAILED CONTENT:")
            logger.info("=" * 80)
            
            # Method Card Details
            if result.method_card:
                logger.info("🔬 METHOD CARD:")
                logger.info(f"   Study Phase: {getattr(result.method_card, 'study_phase', 'N/A')}")
                logger.info(f"   Design Archetype: {getattr(result.method_card, 'design_archetype', 'N/A')}")
                logger.info(f"   Primary Endpoint: {getattr(result.method_card, 'primary_endpoint', 'N/A')}")
                logger.info(f"   Population: {getattr(result.method_card.estimand, 'population', 'N/A') if result.method_card.estimand else 'N/A'}")
                logger.info(f"   Endpoint: {getattr(result.method_card.estimand, 'endpoint', 'N/A') if result.method_card.estimand else 'N/A'}")
                logger.info(f"   Analysis Set: {getattr(result.method_card, 'analysis_set', {})}")
                logger.info(f"   Design Risks: {getattr(result.method_card, 'design_risks', [])}")
            else:
                logger.info("🔬 METHOD CARD: Not available")
            
            # Results Factsheet Details
            if result.results_factsheet:
                logger.info("📊 RESULTS FACTSHEET:")
                logger.info(f"   Results Count: {len(result.results_factsheet.results)}")
                for i, res in enumerate(result.results_factsheet.results[:3], 1):  # Show first 3 results
                    logger.info(f"   Result {i}: {res.get('metric', 'N/A')} = {res.get('value', 'N/A')} {res.get('units', '')}")
                if len(result.results_factsheet.results) > 3:
                    logger.info(f"   ... and {len(result.results_factsheet.results) - 3} more results")
            else:
                logger.info("📊 RESULTS FACTSHEET: Not available")
            
            # Claims Details
            logger.info("📝 CLAIMS:")
            if result.claims:
                logger.info(f"   Claims Count: {len(result.claims)}")
                for i, claim in enumerate(result.claims[:3], 1):  # Show first 3 claims
                    logger.info(f"   Claim {i}: {getattr(claim, 'text', 'N/A')[:100]}...")
                if len(result.claims) > 3:
                    logger.info(f"   ... and {len(result.claims) - 3} more claims")
            else:
                logger.info("   No claims generated")
            
            # Gate Candidates Details
            logger.info("🚪 GATE CANDIDATES:")
            if result.gate_candidates:
                logger.info(f"   Gate Candidates Count: {len(result.gate_candidates)}")
                for i, gate in enumerate(result.gate_candidates, 1):
                    logger.info(f"   Gate {i}: {gate.gate_id}")
                    logger.info(f"      Proposition: {gate.proposition}")
                    logger.info(f"      Decision Rule: {gate.decision_rule}")
                    logger.info(f"      Gate Family: {gate.gate_family}")
                    logger.info(f"      Confidence: {gate.confidence}")
                    logger.info(f"      Priority: {gate.priority}")
                    logger.info(f"      Measurables: {len(gate.measurables)}")
            else:
                logger.info("   No gate candidates generated")
            
            # Gate Specs Details
            logger.info("📋 GATE SPECIFICATIONS:")
            if result.gate_specs:
                logger.info(f"   Gate Specs Count: {len(result.gate_specs)}")
                for i, spec in enumerate(result.gate_specs, 1):
                    logger.info(f"   Spec {i}: {spec.gate_id}")
                    logger.info(f"      Proposition: {spec.proposition}")
                    logger.info(f"      Decision Rule: {spec.decision_rule}")
                    logger.info(f"      Validation Status: {spec.validation_status}")
                    logger.info(f"      Gate Family: {spec.gate_family}")
            else:
                logger.info("   No gate specifications generated")
            
            # Gate Assessments Details
            logger.info("⚖️ GATE ASSESSMENTS:")
            if result.gate_assessments:
                logger.info(f"   Gate Assessments Count: {len(result.gate_assessments)}")
                for i, assessment in enumerate(result.gate_assessments, 1):
                    logger.info(f"   Assessment {i}: {assessment.gate_id}")
                    logger.info(f"      Status: {assessment.status}")
                    logger.info(f"      Confidence: {assessment.confidence_in_assessment}")
                    logger.info(f"      Assessment Method: {assessment.assessment_method}")
                    if assessment.rationale:
                        logger.info(f"      Rationale: {'; '.join(assessment.rationale[:2])}")  # Show first 2 rationale points
                    if assessment.computed_values:
                        logger.info(f"      Computed Values: {list(assessment.computed_values.keys())}")
            else:
                logger.info("   No gate assessments generated")
            
            # Decision Record Details
            if result.decision_record:
                logger.info("📋 DECISION RECORD:")
                logger.info(f"   Decision: {getattr(result.decision_record, 'decision', 'N/A')}")
                logger.info(f"   Confidence: {getattr(result.decision_record, 'confidence', 'N/A')}")
                logger.info(f"   Rationale: {getattr(result.decision_record, 'rationale', 'N/A')}")
            else:
                logger.info("📋 DECISION RECORD: Not available")
            
            # Evidence Spans Summary
            logger.info("🔍 EVIDENCE SPANS SUMMARY:")
            logger.info(f"   Total Evidence Spans: {len(result.evidence_spans)}")
            if result.evidence_spans:
                span_types = {}
                for span in result.evidence_spans:
                    span_type = getattr(span, 'span_type', 'Unknown')
                    span_types[span_type] = span_types.get(span_type, 0) + 1
                for span_type, count in span_types.items():
                    logger.info(f"   {span_type}: {count}")
            
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"Failed to log study card details: {e}")

    async def _save_study_card_snapshot(self, study_card_id: int, nct_id: str, result):
        """Save a JSON snapshot of the study card to reports directory."""
        try:
            snapshot = {
                'study_card_id': study_card_id,
                'nct_id': nct_id,
                'execution_id': self.ctx.execution_id,
                'generated_at': datetime.now().isoformat(),
                'success': result.success,
                'document_cards_count': len(result.document_cards),
                'evidence_spans_count': len(result.evidence_spans),
                'llm_artifacts_count': len(result.llm_artifacts),
                'deterministic_artifacts_count': len(result.deterministic_artifacts),
                'processing_time_seconds': result.processing_time_seconds,
                'errors': result.errors,
                'warnings': result.warnings
            }
            
            snapshot_file = self.ctx.report_dir / f"study_card_{study_card_id}_{nct_id}.json"
            with open(snapshot_file, 'w') as f:
                json.dump(snapshot, f, indent=2)
                
            logger.debug(f"Study card snapshot saved: {snapshot_file}")
            
        except Exception as e:
            logger.warning(f"Failed to save study card snapshot: {str(e)}")
    
    async def _run_automated_evaluation(self):
        """Run automated evaluation with LLM resolution on generated study cards."""
        logger.info("🎯 Running automated evaluation...")
        
        if not self.ctx.study_card_ids:
            logger.warning("No study cards available for evaluation")
            return
        
        try:
            # Initialize evaluation system lazily
            if self.evaluation_system is None:
                AutomatedEvaluationSystem, AutomatedEvaluationRequest = lazy_import_automated_evaluation()
                self.evaluation_system = AutomatedEvaluationSystem()
            
            # Fetch studies from database
            with get_session() as session:
                studies = session.query(Study).filter(
                    Study.study_id.in_(self.ctx.study_card_ids)
                ).all()
            
            if not studies:
                logger.warning("No studies found in database for evaluation")
                return
            
            # Convert Study objects to dictionaries for automated evaluation
            study_cards = []
            for study in studies:
                study_card = {
                    'study_id': study.study_id,
                    'trial_id': getattr(study, 'trial_id', None),
                    'nct_id': getattr(study, 'nct_id', None),
                    'title': getattr(study, 'title', None),
                    'phase': getattr(study, 'phase', None),
                    'status': getattr(study, 'status', None),
                    'extracted_jsonb': getattr(study, 'extracted_jsonb', {})
                }
                study_cards.append(study_card)
            
            # Prepare evaluation request
            evaluation_request = AutomatedEvaluationRequest(
                study_cards=study_cards,
                use_llm_resolution=True,  # Enable LLM resolution for final rankings
                resolution_context=f"E2E execution {self.ctx.execution_id}"
            )
            
            # Run automated evaluation
            eval_start = time.time()
            evaluation_result = await self.evaluation_system.evaluate_study_cards_automated(evaluation_request)
            eval_time = time.time() - eval_start
            
            # Store results
            self.ctx.evaluation_results = evaluation_result
            
            logger.info(f"✅ Automated evaluation completed in {eval_time:.2f}s")
            logger.info(f"   Study cards evaluated: {len(evaluation_result.evaluated_cards)}")
            logger.info(f"   Average confidence: {evaluation_result.average_confidence:.3f}")
            logger.info(f"   High-risk studies: {len(evaluation_result.high_risk_studies)}")
            logger.info(f"   LLM resolution used: {evaluation_result.llm_resolution_summary is not None}")
            
            # Log top-ranked studies
            logger.info("🏆 Top-ranked studies:")
            for i, result in enumerate(evaluation_result.evaluated_cards[:3], 1):
                logger.info(f"   {i}. Study {result.study_id}: Score {result.base_quality_score:.3f}, "
                           f"Confidence {result.base_confidence:.3f}")
            
            # Save evaluation results
            await self._save_evaluation_results(evaluation_result)
            
        except Exception as e:
            error_msg = f"Automated evaluation failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            self.ctx.errors.append(error_msg)
    
    async def _save_evaluation_results(self, evaluation_result):
        """Save evaluation results to reports directory."""
        try:
            eval_data = {
                'execution_id': self.ctx.execution_id,
                'evaluated_at': datetime.now().isoformat(),
                'study_cards_count': len(evaluation_result.evaluated_cards),
                'average_confidence': evaluation_result.average_confidence,
                'high_risk_studies_count': len(evaluation_result.high_risk_studies),
                'llm_resolution_used': evaluation_result.llm_resolution_summary is not None,
                'study_results': [
                    {
                        'study_id': result.study_id,
                        'base_quality_score': result.base_quality_score,
                        'base_confidence': result.base_confidence,
                        'final_ranking_position': result.final_ranking_position
                    }
                    for result in evaluation_result.evaluated_cards
                ],
                'high_risk_studies': [
                    study.study_id for study in evaluation_result.high_risk_studies
                ]
            }
            
            eval_file = self.ctx.report_dir / f"evaluation_results_{self.ctx.execution_id}.json"
            with open(eval_file, 'w') as f:
                json.dump(eval_data, f, indent=2)
                
            logger.info(f"Evaluation results saved: {eval_file}")
            
        except Exception as e:
            logger.warning(f"Failed to save evaluation results: {str(e)}")
    
    async def _generate_final_report(self):
        """Generate final execution report."""
        logger.info("📊 Generating final report...")
        
        execution_time = self.ctx.get_execution_time()
        
        # Create comprehensive report
        report = {
            'execution_summary': {
                'execution_id': self.ctx.execution_id,
                'start_time': self.ctx.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'execution_time_seconds': execution_time,
                'success': len(self.ctx.errors) == 0
            },
            'stopping_conditions': {
                'max_trials': self.ctx.max_trials,
                'time_budget_seconds': self.ctx.time_budget_seconds,
                'at_least_study_cards': self.ctx.at_least_study_cards
            },
            'results': {
                'trials_processed': self.ctx.trials_processed,
                'study_cards_completed': self.ctx.study_cards_completed,
                'study_card_ids': self.ctx.study_card_ids
            },
            'pipeline_results': self.ctx.pipeline_results,
            'evaluation_summary': {
                'completed': self.ctx.evaluation_results is not None,
                'study_cards_evaluated': len(self.ctx.evaluation_results.evaluated_cards) if self.ctx.evaluation_results else 0,
                'average_confidence': self.ctx.evaluation_results.average_confidence if self.ctx.evaluation_results else 0.0
            } if self.ctx.evaluation_results else {'completed': False},
            'errors': self.ctx.errors,
            'warnings': self.ctx.warnings,
            'config_summary': {
                'max_trials': self.ctx.max_trials,
                'time_budget_seconds': self.ctx.time_budget_seconds,
                'at_least_study_cards': self.ctx.at_least_study_cards
            }
        }
        
        # Save report
        report_file = self.ctx.report_dir / f"e2e_execution_report_{self.ctx.execution_id}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"📊 Final report saved: {report_file}")
        
        # Log summary
        logger.info("=" * 80)
        logger.info("E2E EXECUTION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Execution ID: {self.ctx.execution_id}")
        logger.info(f"Duration: {execution_time:.2f} seconds")
        # Success requires both no errors AND meeting study card target
        success = (len(self.ctx.errors) == 0 and 
                  self.ctx.study_cards_completed >= self.ctx.at_least_study_cards)
        logger.info(f"Success: {'✅ YES' if success else '❌ NO'}")
        
        if not success:
            if len(self.ctx.errors) > 0:
                logger.error(f"❌ FAILED: {len(self.ctx.errors)} errors occurred")
            if self.ctx.study_cards_completed < self.ctx.at_least_study_cards:
                logger.error(f"❌ FAILED: Only {self.ctx.study_cards_completed}/{self.ctx.at_least_study_cards} study cards generated")
        logger.info(f"Trials Processed: {self.ctx.trials_processed}")
        logger.info(f"Study Cards Completed: {self.ctx.study_cards_completed}/{self.ctx.at_least_study_cards}")
        
        if self.ctx.study_card_ids:
            logger.info(f"Study Card IDs: {self.ctx.study_card_ids}")
        
        if self.ctx.evaluation_results:
            logger.info(f"Evaluation: {len(self.ctx.evaluation_results.evaluated_cards)} cards evaluated")
            logger.info(f"Average Confidence: {self.ctx.evaluation_results.average_confidence:.3f}")
        
        if self.ctx.errors:
            logger.info("Errors:")
            for error in self.ctx.errors:
                logger.info(f"  ❌ {error}")
        
        if self.ctx.warnings:
            logger.info("Warnings:")
            for warning in self.ctx.warnings:
                logger.info(f"  ⚠️  {warning}")
        
        logger.info("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Real End-to-End Pipeline Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Core arguments
    parser.add_argument('--config', type=str, required=True, help='Path to YAML config file')
    parser.add_argument('--max-trials', type=int, default=5, help='Maximum trials to process')
    parser.add_argument('--time-budget-seconds', type=int, default=900, help='Time budget in seconds (15 minutes)')
    parser.add_argument('--at-least-study-cards', type=int, default=1, help='Stop after generating this many study cards')
    parser.add_argument('--force-full-scan', action='store_true', help='Force full scan instead of incremental')
    
    # Observability
    parser.add_argument('--log-level', choices=['INFO', 'DEBUG', 'WARNING'], default='INFO', help='Log level')
    parser.add_argument('--log-file', type=str, help='Log file path')
    parser.add_argument('--report-dir', type=str, default='reports', help='Directory for reports and snapshots')
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = get_config(args.config)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1
    
    # Create execution context
    ctx = E2EExecutionContext(args, config)
    
    # Run the real E2E pipeline
    runner = RealE2EPipelineRunner(ctx)
    
    try:
        return asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("Execution interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
