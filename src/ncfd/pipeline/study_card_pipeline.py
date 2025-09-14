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
        
        # Check quotes (from evidence spans)
        quote_count = len(result.evidence_spans)
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
            
            # Stage 1.5: Apply document prioritization and rate limiting
            logger.info("Stage 1.5: Applying document prioritization and rate limiting")
            logger.info(f"DEBUG: Passing {len(result.document_cards)} document_cards to prioritization")
            for i, doc_card in enumerate(result.document_cards):
                logger.info(f"DEBUG: document_cards[{i}] = {doc_card.doc_id}")
            prioritized_docs, rate_stats = await self._apply_document_prioritization(
                int(trial_id), result.document_cards, raw_doc_texts, trial_context
            )
            
            # Update document cards and raw texts based on prioritization
            result.document_cards = prioritized_docs['document_cards']
            raw_doc_texts = prioritized_docs['raw_doc_texts']
            
            logger.info(f"Prioritization stats: {rate_stats}")
            
            # Stage 2: Direct LLM processing using our working components
            logger.info("Stage 2: Direct LLM processing")
            
            # Process each document with our working LLM components
            logger.info(f"🔍 STARTING LLM PROCESSING for {len(result.document_cards)} documents")
            for i, doc_card in enumerate(result.document_cards):
                doc_text = raw_doc_texts.get(doc_card.doc_id, "")
                logger.info(f"🔍 PROCESSING DOCUMENT {i+1}/{len(result.document_cards)}: doc_id={doc_card.doc_id}")
                logger.info(f"   📄 Doc text length: {len(doc_text) if doc_text else 0} characters")
                logger.info(f"   📄 Doc text preview: {doc_text[:200] if doc_text else 'NO TEXT'}...")
                logger.info(f"   🔑 Available raw_doc_texts keys: {list(raw_doc_texts.keys())}")
                
                if not doc_text:
                    logger.error(f"❌ ERROR: No text available for document {doc_card.doc_id}")
                    continue
                
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
                    logger.info(f"DEBUG: Method result for doc {doc_card.doc_id}: success={method_result.get('success')}, has_method_card={bool(method_result.get('method_card'))}, field_quotes_count={len(method_result.get('field_quotes', []))}")
                    
                    # Log detailed method card output
                    if method_result.get("method_card"):
                        method_card = method_result["method_card"]
                        logger.info(f"📋 METHOD CARD GENERATED for doc {doc_card.doc_id}:")
                        logger.info(f"   Design Archetype: {getattr(method_card, 'design_archetype', 'N/A')}")
                        logger.info(f"   Population Description: {str(getattr(method_card, 'population_description', 'N/A'))[:100]}...")
                        logger.info(f"   Primary Endpoint: {str(getattr(method_card, 'primary_endpoint', 'N/A'))[:100]}...")
                        logger.info(f"   Sample Size: {getattr(method_card, 'sample_size', 'N/A')}")
                        logger.info(f"   Alpha Level: {getattr(method_card, 'alpha_level', 'N/A')}")
                    
                    # Log detailed field quotes
                    field_quotes = method_result.get('field_quotes', [])
                    if field_quotes:
                        logger.info(f"📝 METHOD FIELD QUOTES ({len(field_quotes)} quotes):")
                        for i, quote in enumerate(field_quotes):
                            logger.info(f"   Quote {i+1}: {quote.field_name} = {str(quote.value)[:50]}...")
                            logger.info(f"      Evidence: {quote.evidence_quote[:100]}...")
                            logger.info(f"      Confidence: {quote.confidence}")
                    
                    if method_result.get("success") and method_result.get("method_card"):
                        result.method_card = method_result["method_card"]
                        
                        # Collect field quotes as evidence spans
                        field_quotes = method_result.get("field_quotes", [])
                        for quote in field_quotes:
                            evidence_span = EvidenceSpan(
                                doc_id=str(doc_card.doc_id),
                                quote=quote.evidence_quote,
                                section="Methods",
                                confidence=quote.confidence
                            )
                            result.evidence_spans.append(evidence_span)
                        
                        # Store LLM artifacts
                        result.llm_artifacts[f"method_card_{doc_card.doc_id}"] = method_result
                        
                        # Save method card to database
                        await self._save_method_card_to_db(method_result["method_card"])
                        
                        # Save quotes to database
                        await self._save_quotes_to_db(field_quotes, doc_card.doc_id, trial_id)
                        logger.info(f"Method card generated for document {doc_card.doc_id} with {len(field_quotes)} quotes")
                        
                        # Results factsheet generation
                        results_data = {
                            "raw_doc_text": doc_text,
                            "doc_id": doc_card.doc_id,
                            "trial_context": trial_context
                        }
                        results_result = await concurrency_manager.execute_with_concurrency_control(
                            self.llm_results_generator.process, results_data
                        )
                        logger.info(f"DEBUG: Results result for doc {doc_card.doc_id}: success={results_result.get('success')}, has_results_factsheet={bool(results_result.get('results_factsheet'))}, field_quotes_count={len(results_result.get('field_quotes', []))}")
                        
                        # Log detailed results factsheet output
                        if results_result.get("results_factsheet"):
                            results_factsheet = results_result["results_factsheet"]
                            logger.info(f"📊 RESULTS FACTSHEET GENERATED for doc {doc_card.doc_id}:")
                            logger.info(f"   Primary Outcome: {str(getattr(results_factsheet, 'primary_outcome', 'N/A'))[:100]}...")
                            logger.info(f"   Secondary Outcomes: {str(getattr(results_factsheet, 'secondary_outcomes', 'N/A'))[:100]}...")
                            logger.info(f"   Statistical Method: {getattr(results_factsheet, 'statistical_method', 'N/A')}")
                            logger.info(f"   Effect Size: {getattr(results_factsheet, 'effect_size', 'N/A')}")
                            logger.info(f"   P-Value: {getattr(results_factsheet, 'p_value', 'N/A')}")
                            logger.info(f"   Confidence Interval: {getattr(results_factsheet, 'confidence_interval', 'N/A')}")
                        
                        # Log detailed field quotes
                        field_quotes = results_result.get('field_quotes', [])
                        if field_quotes:
                            logger.info(f"📝 RESULTS FIELD QUOTES ({len(field_quotes)} quotes):")
                            for i, quote in enumerate(field_quotes):
                                logger.info(f"   Quote {i+1}: {quote.field_name} = {str(quote.value)[:50]}...")
                                logger.info(f"      Evidence: {quote.evidence_quote[:100]}...")
                                logger.info(f"      Confidence: {quote.confidence}")
                        
                        if results_result.get("success") and results_result.get("results_factsheet"):
                            result.results_factsheet = results_result["results_factsheet"]
                            
                            # Collect field quotes as evidence spans
                            field_quotes = results_result.get("field_quotes", [])
                            for quote in field_quotes:
                                evidence_span = EvidenceSpan(
                                    doc_id=str(doc_card.doc_id),
                                    quote=quote.evidence_quote,
                                    section="Results",
                                    confidence=quote.confidence
                                )
                                result.evidence_spans.append(evidence_span)
                            
                            # Store LLM artifacts
                            result.llm_artifacts[f"results_factsheet_{doc_card.doc_id}"] = results_result
                            
                            # Save results factsheet to database
                            await self._save_results_factsheet_to_db(results_result["results_factsheet"])
                            
                            # Save quotes to database
                            await self._save_quotes_to_db(field_quotes, doc_card.doc_id, trial_id)
                            logger.info(f"Results factsheet generated for document {doc_card.doc_id} with {len(field_quotes)} quotes")
                        
                        # Gate assessment generation
                        gate_data = {
                            "raw_doc_text": doc_text,
                            "doc_id": doc_card.doc_id,
                            "trial_context": trial_context
                        }
                        gate_result = await concurrency_manager.execute_with_concurrency_control(
                            self.llm_gate_generator.process, gate_data
                        )
                        logger.info(f"DEBUG: Gate result for doc {doc_card.doc_id}: success={gate_result.get('success')}, has_gate_assessments={bool(gate_result.get('gate_assessments'))}, field_quotes_count={len(gate_result.get('field_quotes', []))}")
                        
                        # Log detailed gate assessments output
                        if gate_result.get("gate_assessments"):
                            gate_assessments = gate_result["gate_assessments"]
                            logger.info(f"🚪 GATE ASSESSMENTS GENERATED for doc {doc_card.doc_id}:")
                            for i, gate in enumerate(gate_assessments):
                                logger.info(f"   Gate {i+1}: {getattr(gate, 'gate_id', 'Unknown')}")
                                logger.info(f"      Status: {getattr(gate, 'status', 'N/A')}")
                                logger.info(f"      Confidence: {getattr(gate, 'confidence_in_assessment', 'N/A')}")
                                logger.info(f"      Rationale: {'; '.join(getattr(gate, 'rationale', []))[:100]}...")
                        
                        # Log detailed field quotes
                        field_quotes = gate_result.get('field_quotes', [])
                        if field_quotes:
                            logger.info(f"📝 GATE FIELD QUOTES ({len(field_quotes)} quotes):")
                            for i, quote in enumerate(field_quotes):
                                logger.info(f"   Quote {i+1}: {quote.field_name} = {str(quote.value)[:50]}...")
                                logger.info(f"      Evidence: {quote.evidence_quote[:100]}...")
                                logger.info(f"      Confidence: {quote.confidence}")
                        
                        # FIXED: Use gate_assessments (plural) instead of gate_assessment (singular)
                        if gate_result.get("success") and gate_result.get("gate_assessments"):
                            result.gate_assessments.extend(gate_result["gate_assessments"])
                            
                            # Collect field quotes as evidence spans
                            field_quotes = gate_result.get("field_quotes", [])
                            for quote in field_quotes:
                                evidence_span = EvidenceSpan(
                                    doc_id=str(doc_card.doc_id),
                                    quote=quote.evidence_quote,
                                    section="Gates",
                                    confidence=quote.confidence
                                )
                                result.evidence_spans.append(evidence_span)
                            
                            # Store LLM artifacts
                            result.llm_artifacts[f"gate_assessments_{doc_card.doc_id}"] = gate_result
                            
                            # Save gate assessments to database
                            for gate_assessment in gate_result["gate_assessments"]:
                                await self._save_gate_assessment_to_db(gate_assessment, trial_context.get("trial_id"))
                            
                            # Save quotes to database
                            await self._save_quotes_to_db(field_quotes, doc_card.doc_id, trial_id)
                            logger.info(f"Gate assessments generated for document {doc_card.doc_id} with {len(field_quotes)} quotes")
                            
                except Exception as e:
                    logger.warning(f"LLM processing failed for document {doc_card.doc_id}: {e}")
                    result.warnings.append(f"LLM processing failed for document {doc_card.doc_id}: {e}")
            
            logger.info("Direct LLM processing completed")
            
            # Log comprehensive summary of all generated artifacts
            logger.info("🎯 STUDY CARD PIPELINE SUMMARY:")
            logger.info(f"   📄 Documents Processed: {len(result.document_cards)}")
            logger.info(f"   📋 Method Cards Generated: {1 if result.method_card else 0}")
            logger.info(f"   📊 Results Factsheets Generated: {1 if result.results_factsheet else 0}")
            logger.info(f"   🚪 Gate Assessments Generated: {len(result.gate_assessments)}")
            logger.info(f"   📝 Total Evidence Spans: {len(result.evidence_spans)}")
            logger.info(f"   🔧 LLM Artifacts Stored: {len(result.llm_artifacts)}")
            
            # Add warnings for empty artifacts
            if not result.method_card:
                logger.warning("⚠️  WARNING: No method card generated!")
            if not result.results_factsheet:
                logger.warning("⚠️  WARNING: No results factsheet generated!")
            if not result.gate_assessments:
                logger.warning("⚠️  WARNING: No gate assessments generated!")
            if not result.evidence_spans:
                logger.warning("⚠️  WARNING: No evidence spans generated!")
            if not result.llm_artifacts:
                logger.warning("⚠️  WARNING: No LLM artifacts stored!")
            
            # Log detailed evidence spans summary
            if result.evidence_spans:
                logger.info("📝 EVIDENCE SPANS BREAKDOWN:")
                section_counts = {}
                for span in result.evidence_spans:
                    section = span.section
                    section_counts[section] = section_counts.get(section, 0) + 1
                for section, count in section_counts.items():
                    logger.info(f"   {section}: {count} quotes")
            
            # Log LLM artifacts summary
            if result.llm_artifacts:
                logger.info("🔧 LLM ARTIFACTS SUMMARY:")
                for artifact_key, artifact_data in result.llm_artifacts.items():
                    logger.info(f"   {artifact_key}: {type(artifact_data).__name__}")
            
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
                logger.info("✅ Study card passed quality gate validation")
                logger.info("🎉 QUALITY GATE VALIDATION DETAILS:")
                logger.info(f"   📄 Documents Analyzed: {len(result.document_cards)} (≥ 1 required)")
                logger.info(f"   📝 Quotes Extracted: {len(result.evidence_spans)} (≥ 3 required)")
                logger.info(f"   📋 Method Card: {'✅ Generated' if result.method_card else '❌ Missing'}")
                logger.info(f"   📊 Results Factsheet: {'✅ Generated' if result.results_factsheet else '❌ Missing'}")
                logger.info(f"   🚪 Gate Assessments: {'✅ Generated' if result.gate_assessments else '❌ Missing'}")
                logger.info(f"   🔧 LLM Artifacts: {len(result.llm_artifacts)} (≥ 1 required)")
            
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
                    'analysis_set': json.dumps(getattr(method_card, 'analysis_set', None)) if getattr(method_card, 'analysis_set', None) is not None else None,
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
        """Save gate assessment to database with upsert to handle unique constraint violations."""
        try:
            from ncfd.db.session import session_scope
            from sqlalchemy import text
            
            with session_scope() as session:
                # Use upsert to handle unique constraint violations
                session.execute(text("""
                    INSERT INTO gates (
                        trial_id, g_id, fired_bool, supporting_s_ids, lr_used, rationale_text
                    ) VALUES (
                        :trial_id, :g_id, :fired_bool, :supporting_s_ids, :lr_used, :rationale_text
                    )
                    ON CONFLICT (trial_id, g_id) DO UPDATE SET
                        fired_bool = EXCLUDED.fired_bool,
                        supporting_s_ids = EXCLUDED.supporting_s_ids,
                        lr_used = EXCLUDED.lr_used,
                        rationale_text = EXCLUDED.rationale_text
                """), {
                    'trial_id': trial_id,
                    'g_id': getattr(gate_assessment, 'gate_id', 'G1'),
                    'fired_bool': getattr(gate_assessment, 'status', 'UNCERTAIN') == 'PASS',
                    'supporting_s_ids': None,  # Not available in GateAssessment model
                    'lr_used': None,  # Not available in GateAssessment model
                    'rationale_text': '; '.join(getattr(gate_assessment, 'rationale', [])) if getattr(gate_assessment, 'rationale', []) else None
                })
                session.commit()
                logger.info(f"Gate assessment upserted to database for trial_id: {trial_id}, gate_id: {getattr(gate_assessment, 'gate_id', 'G1')}, status: {getattr(gate_assessment, 'status', 'UNCERTAIN')}")
        except Exception as e:
            logger.error(f"Failed to save gate assessment to database: {e}")
    
    async def _save_quotes_to_db(self, field_quotes, doc_id, trial_id):
        """Save field quotes to evidence_spans table."""
        try:
            from ncfd.db.session import session_scope
            from sqlalchemy import text
            
            if not field_quotes:
                logger.info(f"No field quotes to save for doc_id: {doc_id}")
                return
            
            with session_scope() as session:
                # Insert quotes into evidence_spans table
                for quote in field_quotes:
                    session.execute(text("""
                        INSERT INTO evidence_spans (
                            doc_id, quote, section, confidence, created_at, updated_at
                        ) VALUES (
                            :doc_id, :quote, :section, :confidence, NOW(), NOW()
                        )
                    """), {
                        'doc_id': str(doc_id),  # Convert to string as per table schema
                        'quote': getattr(quote, 'evidence_quote', ''),
                        'section': getattr(quote, 'section', 'Unknown'),
                        'confidence': getattr(quote, 'confidence', 0.8)
                    })
                session.commit()
                logger.info(f"Saved {len(field_quotes)} quotes to evidence_spans table for doc_id: {doc_id}, trial_id: {trial_id}")
        except Exception as e:
            logger.error(f"Failed to save quotes to database: {e}")
    
    
    async def _apply_document_prioritization(self, trial_id: int, document_cards: List, raw_doc_texts: Dict, trial_context: Dict[str, Any]) -> Tuple[Dict, Dict]:
        """
        Apply document prioritization and rate limiting to retrieved documents.
        
        Args:
            trial_id: Trial ID
            document_cards: List of document cards from retrieval
            raw_doc_texts: Dictionary of raw document texts
            trial_context: Trial context information
            
        Returns:
            Tuple of (prioritized_docs, processing_stats)
        """
        try:
            from ncfd.db.session import session_scope
            from ncfd.db.models import Document, DocumentText, DocumentLink
            
            with session_scope() as session:
                # Get all documents linked to this trial with R/S scores via TrialDocCandidate
                from ncfd.db.models import TrialDocCandidate
                documents = session.query(Document, DocumentText).outerjoin(
                    DocumentText, Document.doc_id == DocumentText.doc_id
                ).join(
                    TrialDocCandidate, Document.doc_id == TrialDocCandidate.doc_id
                ).filter(
                    TrialDocCandidate.trial_id == trial_id,
                    TrialDocCandidate.stage == 'U1_abstract',  # Only U1_abstract stage has abstracts and R/S scores
                    TrialDocCandidate.selected == True
                ).all()
                
                if not documents:
                    logger.warning(f"No documents found for trial {trial_id}")
                    return {'document_cards': [], 'raw_doc_texts': {}}, {
                        "total_documents": 0, 
                        "total_candidates": 0,
                        "selected_documents": 0,
                        "priority_counts": {},
                        "text_availability": {},
                        "rs_score_stats": {},
                        "rate_limit_applied": False
                    }
                
                # Convert to processing candidates with prioritization
                candidates = []
                logger.info(f"DEBUG: Processing {len(documents)} documents from database query")
                for i, (doc, doc_text) in enumerate(documents):
                    # Check text availability
                    has_full_text = bool(doc_text and doc_text.fulltext_text and len(doc_text.fulltext_text.strip()) > 0)
                    has_abstract = bool(doc_text and doc_text.abstract_text and len(doc_text.abstract_text.strip()) > 0)
                    
                    # Determine priority based on R/S scores and text availability
                    priority = self._determine_document_priority(
                        doc.r_score, doc.r_tier, doc.s_score, doc.s_tier,
                        has_full_text, has_abstract
                    )
                    
                    logger.info(f"DEBUG: Document {i+1}: doc_id={doc.doc_id}, priority={priority}, has_text={has_full_text or has_abstract}")
                    
                    # DEBUG: Log prioritization details
                    logger.info(f"DEBUG: Doc {doc.doc_id} (PMID {doc.pmid}): R={doc.r_score} ({doc.r_tier}), S={doc.s_score} ({doc.s_tier}), has_full_text={has_full_text}, has_abstract={has_abstract}, priority={priority}")
                    
                    # Calculate processing score
                    processing_score = self._calculate_processing_score(
                        doc.r_score, doc.s_score, has_full_text, has_abstract,
                        len(doc_text.fulltext_text) if doc_text and doc_text.fulltext_text else 0,
                        len(doc_text.abstract_text) if doc_text and doc_text.abstract_text else 0
                    )
                    
                    candidate = {
                        'doc_id': doc.doc_id,
                        'pmid': doc.pmid,
                        'title': doc.title,
                        'r_score': float(doc.r_score) if doc.r_score else 0.0,
                        'r_tier': doc.r_tier,
                        's_score': float(doc.s_score) if doc.s_score else 0.0,
                        's_tier': doc.s_tier,
                        'has_full_text': has_full_text,
                        'has_abstract': has_abstract,
                        'priority': priority,
                        'processing_score': processing_score,
                        'fulltext_text': doc_text.fulltext_text if doc_text else None,
                        'abstract_text': doc_text.abstract_text if doc_text else None
                    }
                    candidates.append(candidate)
                
                # Sort candidates by priority and processing score
                sorted_candidates = self._sort_document_candidates(candidates)
                
                # Apply rate limiting
                selected_candidates = self._apply_document_rate_limits(sorted_candidates)
                
                # Generate processing statistics
                stats = self._generate_document_processing_stats(documents, candidates, selected_candidates)
                
                # Convert selected candidates back to document cards and raw texts
                prioritized_doc_cards = []
                prioritized_raw_texts = {}
                
                for candidate in selected_candidates:
                    # Find matching document card from original retrieval
                    matching_doc_card = None
                    logger.info(f"DEBUG: Looking for doc_id {candidate['doc_id']} in {len(document_cards)} document_cards")
                    for doc_card in document_cards:
                        logger.info(f"DEBUG: Checking doc_card.doc_id = {doc_card.doc_id}")
                        if doc_card.doc_id == candidate['doc_id']:
                            matching_doc_card = doc_card
                            break
                    
                    if matching_doc_card:
                        prioritized_doc_cards.append(matching_doc_card)
                        # Always prioritize EnhancedRetriever's raw text first (it has the full retrieved text)
                        if candidate['doc_id'] in raw_doc_texts and raw_doc_texts[candidate['doc_id']]:
                            prioritized_raw_texts[candidate['doc_id']] = raw_doc_texts[candidate['doc_id']]
                            logger.info(f"DEBUG: Using EnhancedRetriever text for doc_id {candidate['doc_id']} (length: {len(raw_doc_texts[candidate['doc_id']])})")
                        elif candidate['has_full_text'] and candidate['fulltext_text']:
                            prioritized_raw_texts[candidate['doc_id']] = candidate['fulltext_text']
                            logger.info(f"DEBUG: Using database fulltext for doc_id {candidate['doc_id']} (length: {len(candidate['fulltext_text'])})")
                        elif candidate['has_abstract'] and candidate['abstract_text']:
                            prioritized_raw_texts[candidate['doc_id']] = candidate['abstract_text']
                            logger.info(f"DEBUG: Using database abstract for doc_id {candidate['doc_id']} (length: {len(candidate['abstract_text'])})")
                        else:
                            prioritized_raw_texts[candidate['doc_id']] = ""
                            logger.warning(f"DEBUG: No text available for doc_id {candidate['doc_id']}")
                
                logger.info(f"Document prioritization applied: {len(prioritized_doc_cards)} documents selected from {len(candidates)} candidates")
                
                return {
                    'document_cards': prioritized_doc_cards,
                    'raw_doc_texts': prioritized_raw_texts
                }, stats
                
        except Exception as e:
            logger.error(f"Error applying document prioritization for trial {trial_id}: {e}")
            return {'document_cards': document_cards, 'raw_doc_texts': raw_doc_texts}, {"error": str(e)}
    
    def _determine_document_priority(self, r_score, r_tier, s_score, s_tier, has_full_text, has_abstract):
        """Determine document priority based on R/S scores and text availability."""
        
        # Convert tiers to scores if scores are missing
        if r_score is None and r_tier:
            r_score = self._tier_to_score(r_tier)
        if s_score is None and s_tier:
            s_score = self._tier_to_score(s_tier)
        
        # Default to low scores if missing
        r_score = r_score or 0.0
        s_score = s_score or 0.0
        
        # High priority: R≥2 AND S≥2 AND has text (full text preferred, abstract acceptable)
        if (r_score >= 0.6 and s_score >= 0.6 and (has_full_text or has_abstract)):
            return "HIGH"
        
        # Medium priority: R≥2 OR S≥2 AND has text (full text preferred, abstract acceptable)
        if ((r_score >= 0.6 or s_score >= 0.6) and (has_full_text or has_abstract)):
            return "MEDIUM"
        
        # Low priority: R≥1 OR S≥1 AND has text (full text preferred, abstract acceptable)
        if ((r_score >= 0.4 or s_score >= 0.4) and (has_full_text or has_abstract)):
            return "LOW"
        
        # Fallback: Any R/S score with abstract only (no full text)
        if ((r_score >= 0.4 or s_score >= 0.4) and has_abstract and not has_full_text):
            return "FALLBACK"
        
        # Default to low priority
        return "LOW"
    
    def _tier_to_score(self, tier):
        """Convert R/S tier to approximate score."""
        tier_mapping = {
            'R0': 0.0, 'R1': 0.4, 'R2': 0.6, 'R3': 0.8,
            'S0': 0.0, 'S1': 0.4, 'S2': 0.6, 'S3': 0.8
        }
        return tier_mapping.get(tier, 0.0)
    
    def _calculate_processing_score(self, r_score, s_score, has_full_text, has_abstract, full_text_length, abstract_length):
        """Calculate overall processing score for document prioritization."""
        
        # Base score from R/S scores
        r_score = float(r_score) if r_score else 0.0
        s_score = float(s_score) if s_score else 0.0
        base_score = (r_score + s_score) / 2.0
        
        # Text availability bonus
        text_bonus = 0.0
        if has_full_text:
            text_bonus += 0.3
            # Bonus for longer full text
            if full_text_length and full_text_length > 1000:
                text_bonus += min(0.2, full_text_length / 10000.0)  # Cap at 0.2
        elif has_abstract:
            text_bonus += 0.1
            # Bonus for longer abstract
            if abstract_length and abstract_length > 200:
                text_bonus += min(0.1, abstract_length / 2000.0)  # Cap at 0.1
        
        # Combine base score and text bonus
        processing_score = base_score + text_bonus
        
        return min(1.0, processing_score)  # Cap at 1.0
    
    def _sort_document_candidates(self, candidates):
        """Sort candidates by priority and processing score."""
        
        def sort_key(candidate):
            # Primary sort: priority (HIGH=1, MEDIUM=2, LOW=3, FALLBACK=4)
            priority_order = {"HIGH": 1, "MEDIUM": 2, "LOW": 3, "FALLBACK": 4}
            priority_value = priority_order.get(candidate['priority'], 5)
            
            # Secondary sort: processing score (higher = better)
            processing_score = candidate['processing_score']
            
            # Tertiary sort: R score (higher = better)
            r_score = candidate['r_score']
            
            # Final sort: S score (higher = better)
            s_score = candidate['s_score']
            
            return (priority_value, -processing_score, -r_score, -s_score)
        
        return sorted(candidates, key=sort_key)
    
    def _apply_document_rate_limits(self, candidates):
        """Apply rate limiting to selected candidates."""
        
        # Get rate limiting config from pipeline config
        max_documents_per_trial = self.config.get('max_documents_per_trial', 20)
        enable_fallback_processing = self.config.get('enable_fallback_processing', True)
        max_fallback_documents = self.config.get('max_fallback_documents', 5)
        
        # Separate candidates by priority
        high_priority = [c for c in candidates if c['priority'] == 'HIGH']
        medium_priority = [c for c in candidates if c['priority'] == 'MEDIUM']
        low_priority = [c for c in candidates if c['priority'] == 'LOW']
        fallback_priority = [c for c in candidates if c['priority'] == 'FALLBACK']
        
        # DEBUG: Log priority counts
        logger.info(f"DEBUG: Priority counts - HIGH: {len(high_priority)}, MEDIUM: {len(medium_priority)}, LOW: {len(low_priority)}, FALLBACK: {len(fallback_priority)}")
        
        selected = []
        
        # Select high priority documents first
        selected.extend(high_priority[:max_documents_per_trial])
        
        # Add medium priority if we have room
        remaining_slots = max_documents_per_trial - len(selected)
        if remaining_slots > 0:
            selected.extend(medium_priority[:remaining_slots])
        
        # Add low priority if we have room
        remaining_slots = max_documents_per_trial - len(selected)
        if remaining_slots > 0:
            selected.extend(low_priority[:remaining_slots])
        
        # Add fallback documents if enabled and we have room
        if enable_fallback_processing:
            remaining_slots = max_documents_per_trial - len(selected)
            if remaining_slots > 0:
                selected.extend(fallback_priority[:min(remaining_slots, max_fallback_documents)])
        
        logger.info(f"Rate limiting applied: {len(selected)} documents selected from {len(candidates)} candidates")
        
        return selected
    
    def _generate_document_processing_stats(self, all_documents, candidates, selected):
        """Generate processing statistics."""
        
        # Count by priority
        priority_counts = {}
        for priority in ["HIGH", "MEDIUM", "LOW", "FALLBACK"]:
            priority_counts[priority] = len([c for c in candidates if c['priority'] == priority])
        
        # Count by text availability
        text_stats = {
            'has_full_text': len([c for c in candidates if c['has_full_text']]),
            'has_abstract_only': len([c for c in candidates if c['has_abstract'] and not c['has_full_text']]),
            'no_text': len([c for c in candidates if not c['has_abstract'] and not c['has_full_text']])
        }
        
        # R/S score statistics
        rs_stats = {
            'high_r_scores': len([c for c in candidates if c['r_score'] >= 0.6]),
            'high_s_scores': len([c for c in candidates if c['s_score'] >= 0.6]),
            'medium_r_scores': len([c for c in candidates if c['r_score'] >= 0.4]),
            'medium_s_scores': len([c for c in candidates if c['s_score'] >= 0.4])
        }
        
        return {
            'total_documents': len(all_documents),
            'total_candidates': len(candidates),
            'selected_documents': len(selected),
            'priority_counts': priority_counts,
            'text_availability': text_stats,
            'rs_score_stats': rs_stats,
            'rate_limit_applied': len(selected) < len(candidates)
        }

    def _execute_retrieval(self, trial_context: Dict[str, Any]) -> Any:
        """Execute document retrieval stage."""
        inputs = {
            "trial_context": trial_context,
            "date_window": trial_context.get("date_window", "2020-2024")
        }
        return self.retriever.process(inputs)
    
