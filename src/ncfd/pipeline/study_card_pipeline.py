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
    MethodAuditor, ResultsDistiller, GateProposer,
    GateValidator, GateAssessor, FdaLens, MemoComposer,
    DeterministicMethodAuditor, DeterministicResultsDistiller
)
from ..extract.workers.retriever_factory import build_retriever
from ..extract.workers.llm.llm_results_drafter import LLMResultsDrafter
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
        self.llm_drafter = LLMResultsDrafter()
        self.provenance_backtracer = ProvenanceBacktracer()
        
        # LLM Path Workers
        self.llm_method_auditor = MethodAuditor()
        self.llm_results_distiller = ResultsDistiller()
        
        # Deterministic Path Workers (hooks available but disabled by default)
        deterministic_enabled = self.config.get('deterministic', {}).get('enabled', False)
        if deterministic_enabled:
            self.deterministic_method_auditor = DeterministicMethodAuditor()
            self.deterministic_results_distiller = DeterministicResultsDistiller()
        else:
            self.deterministic_method_auditor = None
            self.deterministic_results_distiller = None
        
        # Other workers
        self.gate_proposer = GateProposer()
        self.gate_validator = GateValidator()
        self.gate_assessor = GateAssessor()
        self.fda_lens = FdaLens()
        self.memo_composer = MemoComposer()
        
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
    
    def execute(self, trial_id: str, trial_context: Dict[str, Any]) -> StudyCardPipelineResult:
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
            
            # Stage 2: LLM quote generation
            logger.info("Stage 2: LLM quote drafting")
            llm_quotes = []
            for doc_card in result.document_cards:
                doc_text = raw_doc_texts.get(doc_card.doc_id, "")
                if doc_text:
                    quote_result = self._execute_llm_quote_generation(doc_card, doc_text, trial_context)
                    if quote_result.success:
                        # Handle both old "quotes" format and new "results_draft" format
                        if "quotes" in quote_result.output:
                            llm_quotes.extend(quote_result.output.get("quotes", []))
                        elif "results_draft" in quote_result.output:
                            # Extract verbatim quotes from results_draft
                            results_draft = quote_result.output["results_draft"]
                            for res in results_draft.results:
                                if res.get("verbatim_quote"):
                                    llm_quotes.append({
                                        "doc_id": doc_card.doc_id,
                                        "text": res["verbatim_quote"],
                                        "metric": res.get("metric", ""),
                                        "value": res.get("value"),
                                        "confidence": res.get("confidence_llm", 0.8)
                                    })
                    else:
                        result.warnings.append(f"LLM quote generation failed for {doc_card.doc_id}: {quote_result.error_message}")
            
            logger.info(f"Generated {len(llm_quotes)} LLM quotes")
            
            # Store LLM quotes in result for quality gate validation
            result.llm_artifacts['quotes'] = llm_quotes
            
            # Stage 3: Provenance backtracing (quotes → spans)
            logger.info("Stage 3: Provenance backtracing")
            all_evidence_spans = []
            for doc_card in result.document_cards:
                doc_text = raw_doc_texts.get(doc_card.doc_id, "")
                if doc_text:
                    # Filter quotes for this document
                    doc_quotes = [q for q in llm_quotes if q.get("doc_id") == doc_card.doc_id]
                    quote_texts = [q.get("text", q) if isinstance(q, dict) else str(q) for q in doc_quotes]
                    
                    # Backtrace to spans
                    spans = self.provenance_backtracer.backtrace_quotes_to_spans(
                        quotes=quote_texts,
                        raw_doc_text=doc_text,
                        doc_id=doc_card.doc_id
                    )
                    all_evidence_spans.extend(spans)
            
            result.evidence_spans = all_evidence_spans
            logger.info(f"Backtraced {len(result.evidence_spans)} evidence spans")
            
            # Stage 4: Method and Results processing (if spans available)
            if result.evidence_spans:
                logger.info("Stage 4: Method and Results processing")
                
                # LLM Method Auditing
                llm_method_result = self._execute_llm_method_auditing(trial_context, result.evidence_spans)
                if not llm_method_result.success:
                    result.warnings.append(f"LLM Method auditing failed: {llm_method_result.error_message}")
                    llm_method_result = None
                
                # LLM Results Distillation
                llm_results_result = self._execute_llm_results_distillation(result.evidence_spans)
                if not llm_results_result.success:
                    result.warnings.append(f"LLM Results distillation failed: {llm_results_result.error_message}")
                    llm_results_result = None
                
                # Use LLM results directly (no fusion needed in LLM-first mode)
                if llm_method_result and llm_method_result.output:
                    result.method_card = llm_method_result.output.get('method_card')
                
                if llm_results_result and llm_results_result.output:
                    result.results_factsheet = llm_results_result.output.get('results_factsheet')
                
                logger.info("LLM-first processing completed")
            else:
                logger.warning("No evidence spans available - skipping method and results processing")
            
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
    
    def _execute_llm_quote_generation(self, doc_card: DocumentCard, doc_text: str, trial_context: Dict[str, Any]):
        """Execute LLM quote generation for a document."""
        return self.llm_drafter.process({
            "raw_doc_text": doc_text,
            "doc_id": doc_card.doc_id,
            "trial_context": trial_context
        })
    
    def _execute_retrieval(self, trial_context: Dict[str, Any]) -> Any:
        """Execute document retrieval stage."""
        inputs = {
            "trial_context": trial_context,
            "date_window": trial_context.get("date_window", "2020-2024")
        }
        return self.retriever.process(inputs)
    
    def _execute_llm_method_auditing(self, trial_context: Dict[str, Any], 
                                    evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute LLM method auditing stage."""
        inputs = {
            "evidence_spans": evidence_spans,
            "design_json": trial_context.get("design_json", {}),
            "pocket_context": trial_context.get("pocket_context")
        }
        return self.llm_method_auditor.process(inputs)
    
    def _execute_llm_results_distillation(self, evidence_spans: List[EvidenceSpan]) -> Any:
        """Execute LLM results distillation stage."""
        inputs = {
            "evidence_spans": evidence_spans,
            "trial_context": {}
        }
        return self.llm_results_distiller.process(inputs)
