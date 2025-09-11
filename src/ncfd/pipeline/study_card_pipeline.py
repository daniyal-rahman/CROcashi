# src/ncfd/pipeline/study_card_pipeline.py
"""
Study Card Pipeline - LLM-First Architecture

Main pipeline for study card processing using LLM-first approach:
documents + raw text → LLM quotes → backtraced spans → workers
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from ..extract.workers import (
    GateValidator, GateAssessor,
    DeterministicMethodAuditor, DeterministicResultsDistiller
)
from ..extract.workers.retriever_factory import build_retriever
from ..extract.workers.llm.llm_results_factsheet_generator import LLMResultsFactsheetGenerator
from ..extract.workers.provenance_backtracer import ProvenanceBacktracer
from ..extract.models import (
    DocumentCard, EvidenceSpan, Claim, MethodCard, ResultsFactsheet,
    PocketContextCard, GateCandidate, GateSpec, GateAssessment, DecisionRecord
)
from ..extract.validators import GlobalValidator
from ..extract.validators.section_constraints import enforce_section_constraints
from ..extract.normalization import get_metric_registry

logger = logging.getLogger(__name__)


@dataclass
class StudyCardPipelineResult:
    """Result of study card pipeline execution."""
    trial_id: str
    success: bool
    start_time: datetime
    end_time: datetime
    processing_time_seconds: float = field(init=False, default=0.0)
    
    # Pipeline outputs
    document_cards: List[DocumentCard] = field(default_factory=list)
    evidence_spans: List[EvidenceSpan] = field(default_factory=list)
    claims: List[Claim] = field(default_factory=list)
    method_card: Optional[MethodCard] = None
    results_factsheet: Optional[ResultsFactsheet] = None
    gate_candidates: List[GateCandidate] = field(default_factory=list)
    gate_specs: List[GateSpec] = field(default_factory=list)
    gate_assessments: List[GateAssessment] = field(default_factory=list)
    decision_record: Optional[DecisionRecord] = None
    
    # Dual-path and fusion outputs
    ambiguity_ledger: Dict[str, Any] = field(default_factory=dict)
    llm_artifacts: Dict[str, Any] = field(default_factory=dict)
    deterministic_artifacts: Dict[str, Any] = field(default_factory=dict)
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class StudyCardPipeline:
    """Main pipeline for study card processing with LLM-first architecture."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the study card pipeline.
        
        Args:
            config: Configuration dictionary with validation settings
        """
        self.config = config or {}
        self.retriever = build_retriever(self.config)
        
        # Core LLM-first workers
        from ..extract.workers.llm.llm_method_card_generator import LLMMethodCardGenerator
        from ..extract.workers.llm.llm_gate_assessment_generator import LLMGateAssessmentGenerator
        
        self.llm_method_generator = LLMMethodCardGenerator()
        self.llm_results_generator = LLMResultsFactsheetGenerator()
        self.llm_gate_generator = LLMGateAssessmentGenerator()
        self.provenance_backtracer = ProvenanceBacktracer()
        
        # Deterministic Path Workers (hooks available but disabled by default)
        deterministic_enabled = self.config.get('deterministic', {}).get('enabled', False)
        if deterministic_enabled:
            self.deterministic_method_auditor = DeterministicMethodAuditor()
            self.deterministic_results_distiller = DeterministicResultsDistiller()
        else:
            self.deterministic_method_auditor = None
            self.deterministic_results_distiller = None
        
        # Other workers
        self.gate_validator = GateValidator()
        self.gate_assessor = GateAssessor()
        
        # Validation configuration
        validation_config = self.config.get('validation', {})
        self.strict_validation = validation_config.get('strict_validation', True)
        self.fail_fast_on_validation = validation_config.get('fail_fast_on_validation', True)
        self.validation_error_action = validation_config.get('validation_error_action', 'fail')
        self.max_validation_errors = validation_config.get('max_validation_errors', 10)
        
        # Specific validation rules
        self.hard_fail_on_provenance = validation_config.get('hard_fail_on_provenance', True)
        self.hard_fail_on_units = validation_config.get('hard_fail_on_units', True)
        self.hard_fail_on_denominators = validation_config.get('hard_fail_on_denominators', True)
        self.hard_fail_on_sections = validation_config.get('hard_fail_on_sections', True)
        
        logger.info(f"StudyCardPipeline initialized with strict_validation={self.strict_validation}")
    
    def _handle_validation_errors(self, result: StudyCardPipelineResult, 
                                artifact_type: str, errors: List[str]) -> bool:
        """
        Handle validation errors according to configuration.
        
        Args:
            result: Pipeline result object
            artifact_type: Type of artifact being validated
            errors: List of validation errors
            
        Returns:
            True if validation passed (no errors or warnings only), False if hard fail
        """
        if not errors:
            return True
            
        # Determine if these are hard-fail errors based on content
        hard_fail_errors = []
        warning_errors = []
        
        for error in errors:
            # Check if error is related to hard-fail categories
            is_hard_fail = (
                self.hard_fail_on_provenance and any(keyword in error.lower() for keyword in 
                    ['provenance', 'span_ids', 'input_hash', 'missing input_hash', 'no span references'])
                or self.hard_fail_on_units and any(keyword in error.lower() for keyword in 
                    ['units', 'invalid units'])
                or self.hard_fail_on_denominators and any(keyword in error.lower() for keyword in 
                    ['denominator', 'n cannot be default', 'pending_denominator'])
                or self.hard_fail_on_sections and any(keyword in error.lower() for keyword in 
                    ['section', 'missing required field'])
            )
            
            if is_hard_fail:
                hard_fail_errors.append(error)
            else:
                warning_errors.append(error)
        
        # Handle hard-fail errors
        if hard_fail_errors and self.strict_validation:
            result.errors.extend([f"{artifact_type} validation: {error}" for error in hard_fail_errors])
            if self.fail_fast_on_validation:
                return False
        
        # Handle warning errors
        if warning_errors:
            result.warnings.extend([f"{artifact_type} validation: {error}" for error in warning_errors])
        
        # Check if we've exceeded max validation errors
        if len(result.errors) >= self.max_validation_errors:
            result.errors.append(f"Exceeded maximum validation errors ({self.max_validation_errors})")
            return False
        
        return True
    
    def _validate_study_card_quality(self, result: StudyCardPipelineResult) -> Tuple[bool, List[str]]:
        """
        Validate study card quality to prevent degenerate cards.
        
        Args:
            result: Study card pipeline result to validate
            
        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []
        
        # Quality gate thresholds
        quality_config = self.config.get('quality_gate', {})
        min_documents = quality_config.get('min_documents_analyzed', 1)
        min_quotes = quality_config.get('min_quotes', 3)
        min_evidence_spans = quality_config.get('min_evidence_spans', 3)
        min_confidence = quality_config.get('min_confidence', 0.55)
        require_method = quality_config.get('require_method', True)
        require_results = quality_config.get('require_results', True)
        require_gates = quality_config.get('require_gates', True)
        min_llm_artifacts = quality_config.get('min_llm_artifacts', 1)
        
        # Check document analysis
        if len(result.document_cards) < min_documents:
            errors.append(f"Insufficient documents analyzed: {len(result.document_cards)} < {min_documents}")
        
        # Check quotes (estimate from LLM artifacts)
        quote_count = len(result.llm_artifacts.get('quotes', []))
        if quote_count < min_quotes:
            errors.append(f"Insufficient quotes extracted: {quote_count} < {min_quotes}")
        
        # Check evidence spans
        if len(result.evidence_spans) < min_evidence_spans:
            errors.append(f"Insufficient evidence spans: {len(result.evidence_spans)} < {min_evidence_spans}")
        
        # Check method card
        if require_method and not result.method_card:
            errors.append("Method section missing - no method card generated")
        
        # Check results factsheet
        if require_results and not result.results_factsheet:
            errors.append("Results section missing - no results factsheet generated")
        
        # Check gates
        if require_gates and len(result.gate_assessments) == 0:
            errors.append("Gates section missing - no gate assessments generated")
        
        # Check LLM artifacts count
        total_llm_artifacts = len(result.llm_artifacts)
        if total_llm_artifacts < min_llm_artifacts:
            errors.append(f"Insufficient LLM artifacts: {total_llm_artifacts} < {min_llm_artifacts}")
        
        # Check confidence score (calculate from available data)
        if result.claims:
            confidence_scores = [claim.confidence for claim in result.claims if hasattr(claim, 'confidence') and claim.confidence is not None]
            if confidence_scores:
                avg_confidence = sum(confidence_scores) / len(confidence_scores)
                if avg_confidence < min_confidence:
                    errors.append(f"Low confidence score: {avg_confidence:.3f} < {min_confidence}")
            else:
                errors.append("No confidence scores available for validation")
        
        return len(errors) == 0, errors
    
    async def execute(self, trial_id: str, trial_context: Dict[str, Any]) -> StudyCardPipelineResult:
        """Execute the complete study card pipeline with LLM-first architecture."""
        start_time = datetime.now(timezone.utc)
        result = StudyCardPipelineResult(
            trial_id=trial_id,
            success=False,
            start_time=start_time,
            end_time=start_time
        )
        
        try:
            logger.info(f"Starting LLM-first study card pipeline for trial {trial_id}")
            
            # Stage 1: Document retrieval (docs + raw text only)
            logger.info("Stage 1: Document retrieval (LLM-first mode)")
            retrieval_result = self._execute_retrieval(trial_context)
            if not retrieval_result.success:
                result.errors.append(f"Document retrieval failed: {retrieval_result.error_message}")
                return result
            
            result.document_cards = retrieval_result.output.get("document_cards", [])
            raw_doc_texts = retrieval_result.output.get("raw_doc_texts", {})
            
            logger.info(f"Retrieved {len(result.document_cards)} documents with {len(raw_doc_texts)} raw texts")
            
            # Stage 2: Direct LLM processing using our working components
            logger.info("Stage 2: Direct LLM processing")
            
            # Process each document with our working LLM components
            for doc_card in result.document_cards:
                doc_text = raw_doc_texts.get(doc_card.doc_id, "")
                if doc_text:
                    # Use our working LLM components with concurrency control
                    try:
                        from ncfd.llm.concurrency_manager import concurrency_manager
                        
                        # Method card generation
                        method_data = {
                            "raw_doc_text": doc_text,
                            "doc_id": doc_card.doc_id,
                            "trial_context": trial_context
                        }
                        method_result = await concurrency_manager.execute_with_concurrency_control(
                            self.llm_method_generator.process, method_data
                        )
                        if method_result.get("success") and method_result.get("method_card"):
                            result.method_card = method_result["method_card"]
                            # Save method card to database
                            await self._save_method_card_to_db(method_result["method_card"])
                            logger.info(f"Method card generated for document {doc_card.doc_id}")
                        
                        # Results factsheet generation
                        results_data = {
                            "raw_doc_text": doc_text,
                            "doc_id": doc_card.doc_id,
                            "trial_context": trial_context
                        }
                        results_result = await concurrency_manager.execute_with_concurrency_control(
                            self.llm_results_generator.process, results_data
                        )
                        if results_result.get("success") and results_result.get("results_factsheet"):
                            result.results_factsheet = results_result["results_factsheet"]
                            # Save results factsheet to database
                            await self._save_results_factsheet_to_db(results_result["results_factsheet"])
                            logger.info(f"Results factsheet generated for document {doc_card.doc_id}")
                        
                        # Gate assessment generation
                        gate_data = {
                            "raw_doc_text": doc_text,
                            "doc_id": doc_card.doc_id,
                            "trial_context": trial_context
                        }
                        gate_result = await concurrency_manager.execute_with_concurrency_control(
                            self.llm_gate_generator.process, gate_data
                        )
                        if gate_result.get("success") and gate_result.get("gate_assessment"):
                            result.gate_assessments.append(gate_result["gate_assessment"])
                            # Save gate assessment to database
                            await self._save_gate_assessment_to_db(gate_result["gate_assessment"], trial_context.get("trial_id"))
                            logger.info(f"Gate assessment generated for document {doc_card.doc_id}")
                            
                    except Exception as e:
                        logger.warning(f"LLM processing failed for document {doc_card.doc_id}: {e}")
                        result.warnings.append(f"LLM processing failed for document {doc_card.doc_id}: {e}")
            
            logger.info("Direct LLM processing completed")
            
            # Stage: Quality Gate Validation
            logger.info("Final Stage: Quality gate validation")
            is_valid, quality_errors = self._validate_study_card_quality(result)
            
            if not is_valid:
                logger.error(f"Study card failed quality gate validation: {quality_errors}")
                result.errors.extend([f"Quality gate: {error}" for error in quality_errors])
                
                # Check if we should fail hard or just warn
                quality_config = self.config.get('quality_gate', {})
                fail_on_quality_gate = quality_config.get('fail_on_validation', True)
                
                if fail_on_quality_gate:
                    result.success = False
                    result.end_time = datetime.now(timezone.utc)
                    result.processing_time_seconds = (result.end_time - result.start_time).total_seconds()
                    logger.error(f"Pipeline failed due to quality gate violations for trial {trial_id}")
                    return result
                else:
                    logger.warning(f"Quality gate violations detected but configured to continue for trial {trial_id}")
                    result.warnings.extend([f"Quality gate warning: {error}" for error in quality_errors])
            else:
                logger.info("Study card passed quality gate validation")
            
            # Complete the pipeline
            result.success = True
            result.end_time = datetime.now(timezone.utc)
            result.processing_time_seconds = (result.end_time - result.start_time).total_seconds()
            
            logger.info(f"Study card pipeline completed successfully for trial {trial_id}")
            logger.info(f"Generated {len(result.document_cards)} document cards, {len(result.evidence_spans)} evidence spans")
            if result.method_card:
                logger.info("Method card generated successfully")
            if result.results_factsheet:
                logger.info("Results factsheet generated successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"Study card pipeline failed for trial {trial_id}: {str(e)}")
            result.errors.append(f"Pipeline execution failed: {str(e)}")
            result.end_time = datetime.now(timezone.utc)
            result.processing_time_seconds = (result.end_time - result.start_time).total_seconds()
            return result
    
    async def _save_method_card_to_db(self, method_card):
        """Save method card to database."""
        try:
            import json
            from ncfd.db.session import session_scope
            from sqlalchemy import text
            
            with session_scope() as session:
                # Insert method card into database
                session.execute(text("""
                    INSERT INTO method_cards (
                        doc_id, design_archetype, is_blinded, analysis_set, population_description,
                        stratification_factors, covariate_adjustment, primary_endpoint, secondary_endpoints,
                        summary_measure, alpha_level, is_one_sided, multiplicity_adjustment,
                        sample_size_reassessment, interim_looks, interim_timing, spending_function,
                        stop_rules, missingness_assumption, missingness_pattern, imputation_method,
                        estimand, intercurrent_events_policy, endpoint_ascertainment, assessment_interval,
                        adjudication_committee, created_at, updated_at
                    ) VALUES (
                        :doc_id, :design_archetype, :is_blinded, :analysis_set, :population_description,
                        :stratification_factors, :covariate_adjustment, :primary_endpoint, :secondary_endpoints,
                        :summary_measure, :alpha_level, :is_one_sided, :multiplicity_adjustment,
                        :sample_size_reassessment, :interim_looks, :interim_timing, :spending_function,
                        :stop_rules, :missingness_assumption, :missingness_pattern, :imputation_method,
                        :estimand, :intercurrent_events_policy, :endpoint_ascertainment, :assessment_interval,
                        :adjudication_committee, NOW(), NOW()
                    )
                """), {
                    'doc_id': method_card.doc_id,
                    'design_archetype': getattr(method_card, 'design_archetype', None),
                    'is_blinded': getattr(method_card, 'is_blinded', None),
                    'analysis_set': getattr(method_card, 'analysis_set', None),
                    'population_description': getattr(method_card, 'population_description', None),
                    'stratification_factors': json.dumps(getattr(method_card, 'stratification_factors', [])),
                    'covariate_adjustment': json.dumps(getattr(method_card, 'covariate_adjustment', [])),
                    'primary_endpoint': getattr(method_card, 'primary_endpoint', None),
                    'secondary_endpoints': json.dumps(getattr(method_card, 'secondary_endpoints', [])),
                    'summary_measure': getattr(method_card, 'summary_measure', None),
                    'alpha_level': getattr(method_card, 'alpha_level', None),
                    'is_one_sided': getattr(method_card, 'is_one_sided', None),
                    'multiplicity_adjustment': getattr(method_card, 'multiplicity_adjustment', None),
                    'sample_size_reassessment': getattr(method_card, 'sample_size_reassessment', None),
                    'interim_looks': json.dumps(getattr(method_card, 'interim_looks', [])),
                    'interim_timing': getattr(method_card, 'interim_timing', None),
                    'spending_function': getattr(method_card, 'spending_function', None),
                    'stop_rules': json.dumps(getattr(method_card, 'stop_rules', [])),
                    'missingness_assumption': getattr(method_card, 'missingness_assumption', None),
                    'missingness_pattern': getattr(method_card, 'missingness_pattern', None),
                    'imputation_method': getattr(method_card, 'imputation_method', None),
                    'estimand': getattr(method_card, 'estimand', None),
                    'intercurrent_events_policy': getattr(method_card, 'intercurrent_events_policy', None),
                    'endpoint_ascertainment': getattr(method_card, 'endpoint_ascertainment', None),
                    'assessment_interval': getattr(method_card, 'assessment_interval', None),
                    'adjudication_committee': getattr(method_card, 'adjudication_committee', None)
                })
                session.commit()
                logger.info(f"Method card saved to database for doc_id: {method_card.doc_id}")
        except Exception as e:
            logger.error(f"Failed to save method card to database: {e}")
    
    async def _save_results_factsheet_to_db(self, results_factsheet):
        """Save results factsheet to database."""
        try:
            import json
            from ncfd.db.session import session_scope
            from sqlalchemy import text
            
            with session_scope() as session:
                # Insert results factsheet into database
                session.execute(text("""
                    INSERT INTO results_factsheets (
                        doc_id, results, primary_endpoint_results, secondary_endpoint_results,
                        safety_results, primary_analysis_set, secondary_analysis_sets,
                        total_enrolled, completed_primary_endpoint, dropout_rate,
                        follow_up_completion, created_at, updated_at
                    ) VALUES (
                        :doc_id, :results, :primary_endpoint_results, :secondary_endpoint_results,
                        :safety_results, :primary_analysis_set, :secondary_analysis_sets,
                        :total_enrolled, :completed_primary_endpoint, :dropout_rate,
                        :follow_up_completion, NOW(), NOW()
                    )
                """), {
                    'doc_id': results_factsheet.doc_id,
                    'results': json.dumps(getattr(results_factsheet, 'results', [])),
                    'primary_endpoint_results': json.dumps(getattr(results_factsheet, 'primary_endpoint_results', None)),
                    'secondary_endpoint_results': json.dumps(getattr(results_factsheet, 'secondary_endpoint_results', [])),
                    'safety_results': json.dumps(getattr(results_factsheet, 'safety_results', [])),
                    'primary_analysis_set': getattr(results_factsheet, 'primary_analysis_set', None),
                    'secondary_analysis_sets': json.dumps(getattr(results_factsheet, 'secondary_analysis_sets', [])),
                    'total_enrolled': getattr(results_factsheet, 'total_enrolled', None),
                    'completed_primary_endpoint': getattr(results_factsheet, 'completed_primary_endpoint', None),
                    'dropout_rate': getattr(results_factsheet, 'dropout_rate', None),
                    'follow_up_completion': getattr(results_factsheet, 'follow_up_completion', None)
                })
                session.commit()
                logger.info(f"Results factsheet saved to database for doc_id: {results_factsheet.doc_id}")
        except Exception as e:
            logger.error(f"Failed to save results factsheet to database: {e}")
    
    async def _save_gate_assessment_to_db(self, gate_assessment, trial_id):
        """Save gate assessment to database."""
        try:
            from ncfd.db.session import session_scope
            from sqlalchemy import text
            
            with session_scope() as session:
                # Insert gate assessment into database
                session.execute(text("""
                    INSERT INTO gates (
                        trial_id, g_id, fired_bool, supporting_s_ids, lr_used, rationale_text
                    ) VALUES (
                        :trial_id, :g_id, :fired_bool, :supporting_s_ids, :lr_used, :rationale_text
                    )
                """), {
                    'trial_id': trial_id,
                    'g_id': getattr(gate_assessment, 'g_id', 'G1'),
                    'fired_bool': getattr(gate_assessment, 'fired_bool', False),
                    'supporting_s_ids': getattr(gate_assessment, 'supporting_s_ids', None),
                    'lr_used': getattr(gate_assessment, 'lr_used', None),
                    'rationale_text': getattr(gate_assessment, 'rationale_text', None)
                })
                session.commit()
                logger.info(f"Gate assessment saved to database for trial_id: {trial_id}")
        except Exception as e:
            logger.error(f"Failed to save gate assessment to database: {e}")
    
    
    def _execute_retrieval(self, trial_context: Dict[str, Any]) -> Any:
        """Execute document retrieval stage."""
        inputs = {
            "trial_context": trial_context,
            "date_window": trial_context.get("date_window", "2020-2024")
        }
        return self.retriever.process(inputs)
    
