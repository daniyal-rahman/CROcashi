# src/ncfd/pipeline/study_card_pipeline.py
"""
Study Card Pipeline - LLM-First Architecture

Main pipeline for study card processing using LLM-first approach:
documents + raw text → LLM quotes → backtraced spans → workers
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from ..extract.retrieval import build_retriever
from ..extract.generators import LLMResultsFactsheetGenerator
from ..extract.models import (
    DocumentCard, Span, StudyCard, ResultsFactsheet, DecisionRecord
)

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
    evidence_spans: List[Span] = field(default_factory=list)
    study_card: Optional[StudyCard] = None
    results_factsheet: Optional[ResultsFactsheet] = None
    
    # Pattern Families system
    pattern_detections: List[Any] = field(default_factory=list)  # PatternDetection objects
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
        from ..extract.generators import LLMStudyCardGenerator, PatternFamilyDetector
        
        self.llm_study_generator = LLMStudyCardGenerator()
        self.llm_results_generator = LLMResultsFactsheetGenerator()
        self.pattern_detector = PatternFamilyDetector()
        
        
        logger.info("StudyCardPipeline initialized with LLM-first architecture")
    
    
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
        require_patterns = quality_config.get('require_patterns', True)
        min_llm_artifacts = quality_config.get('min_llm_artifacts', 1)
        
        # Check document analysis - always require at least 1 document
        if len(result.document_cards) < max(1, min_documents):
            errors.append(f"Insufficient documents analyzed: {len(result.document_cards)} < {max(1, min_documents)}")
        
        # Check quotes (from evidence spans)
        quote_count = len(result.evidence_spans)
        if quote_count < min_quotes:
            errors.append(f"Insufficient quotes extracted: {quote_count} < {min_quotes}")
        
        # Check evidence spans
        if len(result.evidence_spans) < min_evidence_spans:
            errors.append(f"Insufficient evidence spans: {len(result.evidence_spans)} < {min_evidence_spans}")
        
        # Check study card - always require if we have documents
        if len(result.document_cards) > 0 and (require_method or not result.study_card):
            if not result.study_card:
                errors.append("Study section missing - no study card generated")
        
        # Check results factsheet - always require if we have documents
        if len(result.document_cards) > 0 and (require_results or not result.results_factsheet):
            if not result.results_factsheet:
                errors.append("Results section missing - no results factsheet generated")
        
        # Check pattern detections
        if require_patterns and len(result.pattern_detections) == 0:
            errors.append("Pattern detections missing - no risk patterns detected")
        
        # Check LLM artifacts count
        total_llm_artifacts = len(result.llm_artifacts)
        if total_llm_artifacts < min_llm_artifacts:
            errors.append(f"Insufficient LLM artifacts: {total_llm_artifacts} < {min_llm_artifacts}")
        
        # Check database persistence (verify artifacts were actually saved)
        db_persistence_errors = self._check_database_persistence(result)
        errors.extend(db_persistence_errors)
        
        
        return len(errors) == 0, errors
    
    def _check_database_persistence(self, result: StudyCardPipelineResult) -> List[str]:
        """Check that artifacts were actually persisted to the database."""
        errors = []
        
        try:
            from ncfd.db.session import session_scope
            from sqlalchemy import text
            
            with session_scope() as session:
                # Check study cards table
                if result.study_card:
                    study_card_count = session.execute(text("SELECT COUNT(*) FROM study_cards WHERE doc_id = :doc_id"), 
                                                     {'doc_id': result.study_card.doc_id}).scalar()
                    if study_card_count == 0:
                        errors.append(f"Study card not persisted to database for doc_id: {result.study_card.doc_id}")
                
                # Check factsheets table
                if result.results_factsheet:
                    factsheet_count = session.execute(text("SELECT COUNT(*) FROM factsheets WHERE doc_id = :doc_id"), 
                                                    {'doc_id': result.results_factsheet.doc_id}).scalar()
                    if factsheet_count == 0:
                        errors.append(f"Results factsheet not persisted to database for doc_id: {result.results_factsheet.doc_id}")
                
                # Check spans table (evidence quotes)
                if result.evidence_spans:
                    doc_ids = [span.doc_id for span in result.evidence_spans]
                    spans_count = session.execute(text("SELECT COUNT(*) FROM spans WHERE doc_id = ANY(:doc_ids)"), 
                                                {'doc_ids': doc_ids}).scalar()
                    if spans_count == 0:
                        errors.append(f"Evidence spans not persisted to database for doc_ids: {doc_ids}")
                
                # Check pattern_detections table
                if result.pattern_detections:
                    pattern_count = session.execute(text("SELECT COUNT(*) FROM pattern_detections WHERE trial_id = :trial_id"), 
                                                  {'trial_id': result.trial_id}).scalar()
                    if pattern_count == 0:
                        errors.append(f"Pattern detections not persisted to database for trial_id: {result.trial_id}")
                        
        except Exception as e:
            errors.append(f"Database persistence check failed: {e}")
        
        return errors
    
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
            
            # Stage 1.6: Full text retrieval for documents with PMCIDs
            logger.info("Stage 1.6: Full text retrieval for documents with PMCIDs")
            await self._retrieve_full_texts(result.document_cards, raw_doc_texts)
            
            # Stage 2: Direct LLM processing using our working components
            logger.info("Stage 2: Direct LLM processing")
            
            # Process each document with our working LLM components
            logger.info(f"🔍 STARTING LLM PROCESSING for {len(result.document_cards)} documents")
            for i, doc_card in enumerate(result.document_cards):
                # Ensure consistent key type for lookup (raw_doc_texts keys are strings)
                doc_id_key = str(doc_card.doc_id)
                doc_text = raw_doc_texts.get(doc_id_key, "")
                logger.info(f"🔍 PROCESSING DOCUMENT {i+1}/{len(result.document_cards)}: doc_id={doc_card.doc_id} (key={doc_id_key})")
                logger.info(f"   📄 Doc text length: {len(doc_text) if doc_text else 0} characters")
                logger.info(f"   📄 Doc text preview: {doc_text[:200] if doc_text else 'NO TEXT'}...")
                logger.info(f"   🔑 Available raw_doc_texts keys: {list(raw_doc_texts.keys())}")
                logger.info(f"   🔍 Key lookup: '{doc_id_key}' in raw_doc_texts = {doc_id_key in raw_doc_texts}")
                
                if not doc_text:
                    logger.error(f"❌ ERROR: No text available for document {doc_card.doc_id} (key={doc_id_key})")
                    logger.error(f"   Available keys: {list(raw_doc_texts.keys())}")
                    continue
                
                # Use our working LLM components with concurrency control
                try:
                    from ncfd.llm.concurrency_manager import concurrency_manager
                    
                    # Study card generation
                    study_data = {
                        "raw_doc_text": doc_text,
                        "doc_id": doc_card.doc_id,
                        "trial_context": trial_context
                    }
                    study_result = await concurrency_manager.execute_with_concurrency_control(
                        self.llm_study_generator.process, study_data
                    )
                    logger.info(f"DEBUG: Study result for doc {doc_card.doc_id}: success={study_result.get('success')}, has_study_card={bool(study_result.get('study_card'))}, field_quotes_count={len(study_result.get('field_quotes', []))}")
                    
                    # Log detailed study card output
                    if study_result.get("study_card"):
                        study_card = study_result["study_card"]
                        logger.info(f"📋 STUDY CARD GENERATED for doc {doc_card.doc_id}:")
                        logger.info(f"   Design Archetype: {getattr(study_card, 'design_archetype', 'N/A')}")
                        logger.info(f"   Population Description: {str(getattr(study_card, 'population_description', 'N/A'))[:100]}...")
                        logger.info(f"   Primary Endpoint: {str(getattr(study_card, 'primary_endpoint', 'N/A'))[:100]}...")
                        logger.info(f"   Sample Size: {getattr(study_card, 'sample_size', 'N/A')}")
                        logger.info(f"   Alpha Level: {getattr(study_card, 'alpha_level', 'N/A')}")
                    
                    # Log detailed field quotes
                    field_quotes = study_result.get('field_quotes', [])
                    if field_quotes:
                        logger.info(f"📝 STUDY FIELD QUOTES ({len(field_quotes)} quotes):")
                        for i, quote in enumerate(field_quotes):
                            logger.info(f"   Quote {i+1}: {quote.field_name} = {str(quote.value)[:50]}...")
                            logger.info(f"      Evidence: {quote.evidence_quote[:100]}...")
                            logger.info(f"      Confidence: {quote.confidence}")
                    
                    if study_result.get("success") and study_result.get("study_card"):
                        result.study_card = study_result["study_card"]
                        
                        # Collect field quotes as evidence spans
                        field_quotes = study_result.get("field_quotes", [])
                        for quote in field_quotes:
                            evidence_span = Span(
                                doc_id=str(doc_card.doc_id),
                                quote=quote.evidence_quote,
                                section="Methods",
                                confidence=quote.confidence
                            )
                            result.evidence_spans.append(evidence_span)
                        
                        # Store LLM artifacts
                        result.llm_artifacts[f"study_card_{doc_card.doc_id}"] = study_result
                        
                        # Save study card to database
                        await self._save_study_card_to_db(study_result["study_card"])
                        
                        # Save quotes to database
                        await self._save_quotes_to_db(field_quotes, doc_card.doc_id, trial_id)
                        logger.info(f"Study card generated for document {doc_card.doc_id} with {len(field_quotes)} quotes")
                        
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
                                evidence_span = Span(
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
                        
                        # Pattern detection generation
                        pattern_data = {
                            "raw_doc_text": doc_text,
                            "doc_id": doc_card.doc_id,
                            "trial_context": trial_context
                        }
                        pattern_result = await concurrency_manager.execute_with_concurrency_control(
                            self.pattern_detector.process, pattern_data
                        )
                        logger.info(f"DEBUG: Pattern result for doc {doc_card.doc_id}: success={pattern_result.get('success')}, has_pattern_detections={bool(pattern_result.get('pattern_detections'))}")
                        
                        # Log detailed pattern detections output
                        if pattern_result.get("pattern_detections"):
                            pattern_detections = pattern_result["pattern_detections"]
                            logger.info(f"🔍 PATTERN DETECTIONS GENERATED for doc {doc_card.doc_id}:")
                            for i, detection in enumerate(pattern_detections):
                                logger.info(f"   Pattern {i+1}: {getattr(detection, 'pattern_id', 'Unknown')}")
                                logger.info(f"      Family: {getattr(detection, 'family_id', 'N/A')}")
                                logger.info(f"      Severity: {getattr(detection, 'severity', 'N/A')}")
                                logger.info(f"      Confidence: {getattr(detection, 'confidence', 'N/A')}")
                                logger.info(f"      Rationale: {getattr(detection, 'rationale', 'N/A')[:100]}...")
                        
                        # Store pattern detections for later scoring
                        if pattern_result.get("pattern_detections"):
                            result.pattern_detections.extend(pattern_result["pattern_detections"])
                            
                            # Store LLM artifacts
                            result.llm_artifacts[f"pattern_detections_{doc_card.doc_id}"] = pattern_result
                            
                            # Save pattern detections to database
                            for pattern_detection in pattern_result["pattern_detections"]:
                                await self._save_pattern_detection_to_db(pattern_detection, trial_context.get("trial_id"))
                            
                            # Save quotes to database
                            await self._save_quotes_to_db(field_quotes, doc_card.doc_id, trial_id)
                            logger.info(f"Pattern detections generated for document {doc_card.doc_id}")
                            
                except Exception as e:
                    logger.warning(f"LLM processing failed for document {doc_card.doc_id}: {e}")
                    result.warnings.append(f"LLM processing failed for document {doc_card.doc_id}: {e}")
            
            logger.info("Direct LLM processing completed")
            
            # Log comprehensive summary of all generated artifacts
            logger.info("🎯 STUDY CARD PIPELINE SUMMARY:")
            logger.info(f"   📄 Documents Processed: {len(result.document_cards)}")
            logger.info(f"   📋 Study Cards Generated: {1 if result.study_card else 0}")
            logger.info(f"   📊 Results Factsheets Generated: {1 if result.results_factsheet else 0}")
            logger.info(f"   🚪 Pattern Detections Generated: {len(result.pattern_detections)}")
            logger.info(f"   📝 Total Evidence Spans: {len(result.evidence_spans)}")
            logger.info(f"   🔧 LLM Artifacts Stored: {len(result.llm_artifacts)}")
            
            # Add warnings for empty artifacts
            if not result.study_card:
                logger.warning("⚠️  WARNING: No study card generated!")
            if not result.results_factsheet:
                logger.warning("⚠️  WARNING: No results factsheet generated!")
            if not result.pattern_detections:
                logger.warning("⚠️  WARNING: No pattern detections generated!")
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
            
            # Get quality config for logging
            quality_config = self.config.get('quality_gate', {})
            min_quotes = quality_config.get('min_quotes', 3)
            min_llm_artifacts = quality_config.get('min_llm_artifacts', 1)
            
            if not is_valid:
                logger.error(f"Study card failed quality gate validation: {quality_errors}")
                result.errors.extend([f"Quality gate: {error}" for error in quality_errors])
                
                # Check if we should fail hard or just warn
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
                logger.info(f"   📝 Quotes Extracted: {len(result.evidence_spans)} (≥ {min_quotes} required)")
                logger.info(f"   📋 Study Card: {'✅ Generated' if result.study_card else '❌ Missing'}")
                logger.info(f"   📊 Results Factsheet: {'✅ Generated' if result.results_factsheet else '❌ Missing'}")
                logger.info(f"   🔍 Pattern Detections: {'✅ Generated' if result.pattern_detections else '❌ Missing'}")
                logger.info(f"   🔧 LLM Artifacts: {len(result.llm_artifacts)} (≥ {min_llm_artifacts} required)")
            
            # Stage: Decision Record Generation
            logger.info("Final Stage: Decision record generation")
            decision_record = await self._generate_decision_record(result, trial_context)
            result.decision_record = decision_record
            
            if decision_record:
                logger.info("🎯 DECISION RECORD GENERATED:")
                logger.info(f"   Decision: {decision_record.decision}")
                logger.info(f"   Posterior Success: {decision_record.posterior_success}")
                logger.info(f"   Pattern Assessments: {len(decision_record.gates)}")
                logger.info(f"   Risk Factors: {len(decision_record.risk_factors)}")
                logger.info(f"   Mitigation Strategies: {len(decision_record.mitigation_strategies)}")
            else:
                logger.warning("⚠️ No decision record generated")
            
            # Complete the pipeline
            result.success = True
            result.end_time = datetime.now(timezone.utc)
            result.processing_time_seconds = (result.end_time - result.start_time).total_seconds()
            
            logger.info(f"Study card pipeline completed successfully for trial {trial_id}")
            logger.info(f"Generated {len(result.document_cards)} document cards, {len(result.evidence_spans)} evidence spans")
            if result.study_card:
                logger.info("Study card generated and persisted successfully")
            if result.results_factsheet:
                logger.info("Results factsheet generated and persisted successfully")
            if result.pattern_detections:
                logger.info(f"Pattern detections generated and persisted successfully ({len(result.pattern_detections)} patterns)")
            
            return result
            
        except Exception as e:
            logger.error(f"Study card pipeline failed for trial {trial_id}: {str(e)}")
            result.errors.append(f"Pipeline execution failed: {str(e)}")
            result.end_time = datetime.now(timezone.utc)
            result.processing_time_seconds = (result.end_time - result.start_time).total_seconds()
            return result
    
    async def _save_study_card_to_db(self, study_card):
        """Save study card to database."""
        try:
            import json
            from ncfd.db.session import session_scope
            from sqlalchemy import text
            
            with session_scope() as session:
                # Insert study card into database
                session.execute(text("""
                           INSERT INTO study_cards (
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
                    'doc_id': study_card.doc_id,
                    'design_archetype': getattr(study_card, 'design_archetype', None),
                    'is_blinded': getattr(study_card, 'is_blinded', None),
                    'analysis_set': json.dumps(getattr(study_card, 'analysis_set', None)) if getattr(study_card, 'analysis_set', None) is not None else None,
                    'population_description': getattr(study_card, 'population_description', None),
                    'stratification_factors': json.dumps(getattr(study_card, 'stratification_factors', [])),
                    'covariate_adjustment': json.dumps(getattr(study_card, 'covariate_adjustment', [])),
                    'primary_endpoint': getattr(study_card, 'primary_endpoint', None),
                    'secondary_endpoints': json.dumps(getattr(study_card, 'secondary_endpoints', [])),
                    'summary_measure': getattr(study_card, 'summary_measure', None),
                    'alpha_level': getattr(study_card, 'alpha_level', None),
                    'is_one_sided': getattr(study_card, 'is_one_sided', None),
                    'multiplicity_adjustment': getattr(study_card, 'multiplicity_adjustment', None),
                    'sample_size_reassessment': getattr(study_card, 'sample_size_reassessment', None),
                    'interim_looks': json.dumps(getattr(study_card, 'interim_looks', [])),
                    'interim_timing': getattr(study_card, 'interim_timing', None),
                    'spending_function': getattr(study_card, 'spending_function', None),
                    'stop_rules': json.dumps(getattr(study_card, 'stop_rules', [])),
                    'missingness_assumption': getattr(study_card, 'missingness_assumption', None),
                    'missingness_pattern': getattr(study_card, 'missingness_pattern', None),
                    'imputation_method': getattr(study_card, 'imputation_method', None),
                    'estimand': getattr(study_card, 'estimand', None),
                    'intercurrent_events_policy': getattr(study_card, 'intercurrent_events_policy', None),
                    'endpoint_ascertainment': getattr(study_card, 'endpoint_ascertainment', None),
                    'assessment_interval': getattr(study_card, 'assessment_interval', None),
                    'adjudication_committee': getattr(study_card, 'adjudication_committee', None)
                })
                session.commit()
                logger.info(f"Study card saved to database for doc_id: {study_card.doc_id}")
        except Exception as e:
            logger.error(f"Failed to save study card to database: {e}")
    
    async def _save_results_factsheet_to_db(self, results_factsheet):
        """Save results factsheet to database."""
        try:
            import json
            from ncfd.db.session import session_scope
            from sqlalchemy import text
            
            with session_scope() as session:
                # Insert results factsheet into database
                session.execute(text("""
                           INSERT INTO factsheets (
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
    
    
    async def _save_quotes_to_db(self, field_quotes, doc_id, trial_id):
        """Save field quotes to spans table."""
        try:
            from ncfd.db.session import session_scope
            from ncfd.db.models import Span as DBSpan
            
            if not field_quotes:
                logger.info(f"No field quotes to save for doc_id: {doc_id}")
                return
            
            with session_scope() as session:
                # Insert quotes into spans table using ORM
                for quote in field_quotes:
                    db_span = DBSpan(
                        doc_id=int(doc_id),  # Convert to int as per table schema
                        quote=getattr(quote, 'evidence_quote', ''),
                        section=getattr(quote, 'section', 'Unknown'),
                        confidence=getattr(quote, 'confidence', 0.8),
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(db_span)
                session.commit()
                logger.info(f"Saved {len(field_quotes)} quotes to spans table for doc_id: {doc_id}, trial_id: {trial_id}")
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
            
            # Use document_cards as the source of truth instead of database query
            # This ensures we only prioritize documents that were actually retrieved
            if not document_cards:
                logger.warning(f"No document cards provided for trial {trial_id}")
                return {'document_cards': [], 'raw_doc_texts': {}}, {
                    "total_documents": 0, 
                    "total_candidates": 0,
                    "selected_documents": 0,
                    "priority_counts": {},
                    "text_availability": {},
                    "rs_score_stats": {},
                    "rate_limit_applied": False
                }
            
            # Get document details from database for prioritization
            doc_ids = [doc_card.doc_id for doc_card in document_cards]
            
            with session_scope() as session:
                documents = session.query(Document, DocumentText).outerjoin(
                    DocumentText, Document.doc_id == DocumentText.doc_id
                ).filter(Document.doc_id.in_(doc_ids)).all()
                
                # Create a lookup map for document details
                doc_details = {}
                for doc, doc_text in documents:
                    doc_details[doc.doc_id] = {
                        'doc': doc,
                        'doc_text': doc_text,
                        'has_full_text': bool(doc_text and doc_text.fulltext_text and len(doc_text.fulltext_text.strip()) > 0),
                        'has_abstract': bool(doc_text and doc_text.abstract_text and len(doc_text.abstract_text.strip()) > 0)
                    }
                
                # Convert document cards to processing candidates with prioritization
                candidates = []
                logger.info(f"DEBUG: Processing {len(document_cards)} document cards from retrieval")
                
                for i, doc_card in enumerate(document_cards):
                    doc_info = doc_details.get(doc_card.doc_id)
                    if not doc_info:
                        logger.warning(f"No database details found for doc_id {doc_card.doc_id}")
                        continue
                    
                    doc = doc_info['doc']
                    doc_text = doc_info['doc_text']
                    has_full_text = doc_info['has_full_text']
                    has_abstract = doc_info['has_abstract']
                    
                    # Determine priority based on R/S scores and text availability
                    priority = self._determine_document_priority(
                        doc.r_score, doc.r_tier, doc.s_score, doc.s_tier,
                        has_full_text, has_abstract, doc
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
                    for doc_card in document_cards:
                        if doc_card.doc_id == candidate['doc_id']:
                            matching_doc_card = doc_card
                            break
                    
                    if matching_doc_card:
                        prioritized_doc_cards.append(matching_doc_card)
                        # Ensure consistent key type for raw_doc_texts lookup
                        doc_id_key = str(candidate['doc_id'])
                        
                        # Always prioritize EnhancedRetriever's raw text first (it has the full retrieved text)
                        if doc_id_key in raw_doc_texts and raw_doc_texts[doc_id_key]:
                            prioritized_raw_texts[doc_id_key] = raw_doc_texts[doc_id_key]
                            logger.info(f"DEBUG: Using EnhancedRetriever text for doc_id {candidate['doc_id']} (key={doc_id_key}, length: {len(raw_doc_texts[doc_id_key])})")
                        elif candidate['has_full_text'] and candidate['fulltext_text']:
                            prioritized_raw_texts[doc_id_key] = candidate['fulltext_text']
                            logger.info(f"DEBUG: Using database fulltext for doc_id {candidate['doc_id']} (key={doc_id_key}, length: {len(candidate['fulltext_text'])})")
                        elif candidate['has_abstract'] and candidate['abstract_text']:
                            prioritized_raw_texts[doc_id_key] = candidate['abstract_text']
                            logger.info(f"DEBUG: Using database abstract for doc_id {candidate['doc_id']} (key={doc_id_key}, length: {len(candidate['abstract_text'])})")
                        else:
                            prioritized_raw_texts[doc_id_key] = ""
                            logger.warning(f"DEBUG: No text available for doc_id {candidate['doc_id']} (key={doc_id_key})")
                
                logger.info(f"Document prioritization applied: {len(prioritized_doc_cards)} documents selected from {len(candidates)} candidates")
                
                return {
                    'document_cards': prioritized_doc_cards,
                    'raw_doc_texts': prioritized_raw_texts
                }, stats
                
        except Exception as e:
            logger.error(f"Error applying document prioritization for trial {trial_id}: {e}")
            logger.warning("Falling back to simple sort by R/S score")
            
            # Fallback: simple sort by R/S score and limit to top documents
            try:
                from ncfd.db.session import session_scope
                from ncfd.db.models import Document
                
                # Get document details for sorting
                doc_ids = [doc_card.doc_id for doc_card in document_cards]
                with session_scope() as session:
                    documents = session.query(Document).filter(Document.doc_id.in_(doc_ids)).all()
                    doc_lookup = {doc.doc_id: doc for doc in documents}
                
                # Sort by R/S score (convert Decimal to float)
                def sort_key(doc_card):
                    doc = doc_lookup.get(doc_card.doc_id)
                    if not doc:
                        return 0.0
                    r_score = float(doc.r_score) if doc.r_score is not None else 0.0
                    s_score = float(doc.s_score) if doc.s_score is not None else 0.0
                    return (r_score + s_score) / 2.0
                
                sorted_cards = sorted(document_cards, key=sort_key, reverse=True)
                
                # Limit to top documents (configurable, default to 1)
                top_k = getattr(self.config, 'method_docs_top_k', 1)
                limited_cards = sorted_cards[:top_k]
                
                # Filter out obvious non-study documents
                filtered_cards = []
                for doc_card in limited_cards:
                    doc = doc_lookup.get(doc_card.doc_id)
                    if doc and self._is_study_document(doc):
                        filtered_cards.append(doc_card)
                
                # Use filtered cards or fall back to limited cards
                final_cards = filtered_cards if filtered_cards else limited_cards
                
                # Build corresponding raw texts (ensure consistent string keys)
                final_raw_texts = {str(card.doc_id): raw_doc_texts.get(str(card.doc_id), "") for card in final_cards}
                
                logger.info(f"Fallback prioritization: {len(final_cards)} documents selected from {len(document_cards)} candidates")
                
                return {
                    'document_cards': final_cards,
                    'raw_doc_texts': final_raw_texts
                }, {"error": str(e), "fallback_used": True, "documents_selected": len(final_cards)}
                
            except Exception as fallback_error:
                logger.error(f"Fallback prioritization also failed: {fallback_error}")
                # Last resort: return first document only
                single_card = document_cards[:1] if document_cards else []
                single_raw_texts = {str(card.doc_id): raw_doc_texts.get(str(card.doc_id), "") for card in single_card}
                return {'document_cards': single_card, 'raw_doc_texts': single_raw_texts}, {"error": str(e), "fallback_failed": True}
    
    def _determine_document_priority(self, r_score, r_tier, s_score, s_tier, has_full_text, has_abstract, doc=None):
        """Determine document priority based on R/S scores, text availability, and document characteristics."""
        
        # Convert tiers to scores if scores are missing
        if r_score is None and r_tier:
            r_score = self._tier_to_score(r_tier)
        if s_score is None and s_tier:
            s_score = self._tier_to_score(s_tier)
        
        # Convert to float to avoid Decimal + float errors
        r_score = float(r_score) if r_score is not None else 0.0
        s_score = float(s_score) if s_score is not None else 0.0
        
        # Boost priority for documents with PMCID (proxy for full text availability)
        pmcid_boost = 0.0
        if doc and hasattr(doc, 'pmcid') and doc.pmcid:
            pmcid_boost = 0.2
        
        # Boost priority for clinical trial publications
        clinical_trial_boost = 0.0
        if doc and hasattr(doc, 'publication_type') and doc.publication_type:
            pub_type = doc.publication_type.lower()
            if any(term in pub_type for term in ['clinical trial', 'randomized controlled trial', 'controlled clinical trial']):
                clinical_trial_boost = 0.3
        
        # Boost priority for documents with NCT IDs
        nct_boost = 0.0
        if doc and hasattr(doc, 'title') and doc.title:
            title = doc.title.lower()
            if 'nct' in title or 'clinicaltrials.gov' in title:
                nct_boost = 0.2
        
        # Apply boosts
        effective_r_score = r_score + pmcid_boost + clinical_trial_boost + nct_boost
        effective_s_score = s_score + pmcid_boost + clinical_trial_boost + nct_boost
        
        # HIGH priority: Strong R/S scores OR PMCID presence OR clinical trial
        if (effective_r_score >= 0.5 or effective_s_score >= 0.5) and (has_full_text or has_abstract):
            return "HIGH"
        
        # MEDIUM priority: Moderate R/S scores OR PMCID presence
        if (effective_r_score >= 0.3 or effective_s_score >= 0.3) and (has_full_text or has_abstract):
            return "MEDIUM"
        
        # LOW priority: Any R/S score with text
        if (effective_r_score >= 0.1 or effective_s_score >= 0.1) and (has_full_text or has_abstract):
            return "LOW"
        
        # FALLBACK: Any R/S score with abstract only
        if (effective_r_score >= 0.1 or effective_s_score >= 0.1) and has_abstract and not has_full_text:
            return "FALLBACK"
        
        # Default to low priority
        return "LOW"
    
    def _is_study_document(self, doc) -> bool:
        """Filter out obvious non-study documents (news, editorials, etc.)."""
        if not doc:
            return False
        
        # Check publication type
        if hasattr(doc, 'publication_type') and doc.publication_type:
            pub_type = doc.publication_type.lower()
            # Exclude obvious non-study types
            if any(term in pub_type for term in ['news', 'editorial', 'letter', 'comment', 'retraction']):
                return False
        
        # Check title for study indicators
        if hasattr(doc, 'title') and doc.title:
            title = doc.title.lower()
            # Must have some study-related terms
            study_terms = ['study', 'trial', 'clinical', 'research', 'investigation', 'analysis', 'evaluation', 'assessment']
            if not any(term in title for term in study_terms):
                # Allow if it has method/result terms
                method_terms = ['method', 'result', 'outcome', 'efficacy', 'safety', 'effect']
                if not any(term in title for term in method_terms):
                    return False
        
        # Check abstract length (too short might be non-study)
        if hasattr(doc, 'abstract_text') and doc.abstract_text:
            if len(doc.abstract_text.strip()) < 100:  # Very short abstracts are suspicious
                return False
        
        return True
    
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
    
    async def _generate_decision_record(self, result: StudyCardPipelineResult, trial_context: Dict[str, Any]) -> Optional[DecisionRecord]:
        """Generate a comprehensive decision record from gate assessments and other artifacts."""
        try:
            from ..extract.models.decision_record import DecisionRecord
            
            # Create decision record
            decision_record = DecisionRecord(
                trial_id=result.trial_id,
                decision_date=datetime.now(timezone.utc).isoformat(),
                decision_maker="StudyCardPipeline",
                review_committee="AutomatedAnalysis"
            )
            
            # Add pattern detections as gate assessments
            for pattern_detection in result.pattern_detections:
                # Convert pattern severity to probability
                p_pattern = self._convert_pattern_severity_to_probability(pattern_detection.severity)
                
                # Convert pattern detection to gate assessment format
                gate_id = f"{pattern_detection.family_id}_{pattern_detection.pattern_id}"
                # Convert SeverityLevel enum to status (0=grey, 1=yellow, 2=red)
                severity_value = pattern_detection.severity.value
                status = "FAIL" if severity_value >= 2 else "PASS" if severity_value == 0 else "UNCERTAIN"
                
                decision_record.add_gate_assessment(
                    gate_id=gate_id,
                    status=status,
                    p_gate=p_pattern,
                    rationale=f"{pattern_detection.family_id}/{pattern_detection.pattern_id} ({pattern_detection.severity}): {pattern_detection.rationale}"
                )
            
            # Calculate overall success probability
            if decision_record.gates:
                overall_success = decision_record.calculate_overall_success()
                if overall_success is not None:
                    decision_record.set_posterior_success(overall_success)
            
            # Generate comprehensive analysis using synthesis components
            self._generate_comprehensive_analysis(decision_record, result, trial_context)
            
            # Update decision based on pattern assessments
            decision_record._update_decision_from_gates()
            
            logger.info(f"Generated decision record with {len(decision_record.gates)} pattern assessments, decision: {decision_record.decision}")
            return decision_record
            
        except Exception as e:
            logger.error(f"Failed to generate decision record: {e}")
            return None
    
    def _convert_gate_status_to_probability(self, status: str) -> float:
        """Convert gate status to probability score."""
        status_mapping = {
            "PASS": 0.9,      # High confidence pass
            "FAIL": 0.1,      # High confidence fail  
            "UNCERTAIN": 0.5  # Neutral/uncertain
        }
        return status_mapping.get(status, 0.5)
    
    def _convert_pattern_severity_to_probability(self, severity) -> float:
        """Convert pattern severity to probability of success."""
        # Handle SeverityLevel enum (0=grey, 1=yellow, 2=red)
        if hasattr(severity, 'value'):
            severity_value = severity.value
        else:
            # Fallback for string values (shouldn't happen with SeverityLevel enum)
            severity_map = {"grey": 0, "yellow": 1, "red": 2}
            severity_value = severity_map.get(severity, 1)
        
        # Convert severity value to probability (higher severity = lower success probability)
        probability_map = {
            0: 0.9,  # grey - low risk
            1: 0.7,  # yellow - moderate risk  
            2: 0.1   # red - very high risk
        }
        return probability_map.get(severity_value, 0.5)
    
    def _generate_comprehensive_analysis(self, decision_record: DecisionRecord, result: StudyCardPipelineResult, trial_context: Dict[str, Any]) -> None:
        """Generate comprehensive analysis using synthesis components."""
        try:
            
            # Generate risk factors from pattern detections
            risk_factors = []
            for pattern_detection in result.pattern_detections:
                severity_value = pattern_detection.severity.value
                severity_name = pattern_detection.severity.name.lower()  # grey, yellow, amber, red
                
                if severity_value >= 2:  # amber (2) or red (3)
                    risk_factors.append(f"Pattern {pattern_detection.family_id}/{pattern_detection.pattern_id} ({severity_name}): {pattern_detection.rationale}")
                elif severity_value == 1:  # yellow
                    risk_factors.append(f"Pattern {pattern_detection.family_id}/{pattern_detection.pattern_id} (yellow): {pattern_detection.rationale}")
            
            # Add risk factors to decision record
            for risk in risk_factors:
                decision_record.add_risk_factor(risk)
            
            # Generate mitigation strategies
            mitigation_strategies = []
            if decision_record.failed_gates > 0:
                mitigation_strategies.append("Request additional data or clarification for failed pattern assessments")
                mitigation_strategies.append("Consider alternative endpoints or analysis approaches")
            if decision_record.uncertain_gates > 0:
                mitigation_strategies.append("Conduct additional analysis for uncertain pattern assessments")
                mitigation_strategies.append("Seek expert review for ambiguous findings")
            
            # Add mitigation strategies
            for strategy in mitigation_strategies:
                decision_record.add_mitigation_strategy(strategy)
            
            # Generate decision rationale
            rationale_parts = []
            if decision_record.failed_gates > 0:
                rationale_parts.append(f"{decision_record.failed_gates} pattern assessment(s) failed, indicating significant concerns")
            if decision_record.uncertain_gates > 0:
                rationale_parts.append(f"{decision_record.uncertain_gates} pattern assessment(s) uncertain, requiring additional analysis")
            if decision_record.passed_gates > 0:
                rationale_parts.append(f"{decision_record.passed_gates} pattern assessment(s) passed, indicating positive signals")
            
            if rationale_parts:
                decision_record.add_decision_rationale("; ".join(rationale_parts))
            
            logger.info(f"Generated comprehensive analysis: {len(risk_factors)} risk factors, {len(mitigation_strategies)} mitigation strategies")
            
        except Exception as e:
            logger.error(f"Failed to generate comprehensive analysis: {e}")
    
    async def _retrieve_full_texts(self, document_cards: List[DocumentCard], raw_doc_texts: Dict[int, str]) -> None:
        """
        Retrieve full text for documents that have PMCIDs but no full text content.
        
        Args:
            document_cards: List of document cards to process
            raw_doc_texts: Dictionary of doc_id -> text content (will be updated)
        """
        try:
            from ncfd.ingest.pubmed.client import PubMedClient
            from ncfd.db.session import session_scope
            from ncfd.db.models import Document, DocumentText
            
            # Initialize PubMed client with proper async context
            async with PubMedClient() as client:
                # Get documents with PMCIDs but no full text
                documents_to_process = []
                with session_scope() as session:
                    for doc_card in document_cards:
                        doc = session.query(Document).filter(Document.doc_id == doc_card.doc_id).first()
                        if doc and doc.pmcid:
                            # Check if we already have full text
                            doc_text = session.query(DocumentText).filter(DocumentText.doc_id == doc.doc_id).first()
                            has_full_text = bool(doc_text and doc_text.fulltext_text and len(doc_text.fulltext_text.strip()) > 0)
                            
                            if not has_full_text:
                                documents_to_process.append({
                                    'doc_id': doc.doc_id,
                                    'pmid': doc.pmid,
                                    'pmcid': doc.pmcid
                                })
                
                if not documents_to_process:
                    logger.info("No documents need full text retrieval")
                    return
                
                logger.info(f"Retrieving full text for {len(documents_to_process)} documents with PMCIDs")
                
                # Process documents in batches
                batch_size = 5
                for i in range(0, len(documents_to_process), batch_size):
                    batch = documents_to_process[i:i + batch_size]
                    logger.info(f"Processing batch {i//batch_size + 1}: {len(batch)} documents")
                    
                    for doc_info in batch:
                        try:
                            logger.info(f"Retrieving full text for PMID {doc_info['pmid']} (PMCID: {doc_info['pmcid']})")
                            
                            # Try JATS XML first (most comprehensive)
                            full_text = await client.get_pmc_full_text_jats(
                                doc_info['pmcid'], 
                                include_refs=True, 
                                include_captions=True
                            )
                            
                            # Fallback to plain text if JATS fails
                            if not full_text:
                                logger.warning(f"JATS fetch failed for {doc_info['pmcid']}, trying plain text fallback")
                                full_text = await client.get_pmc_full_text(doc_info['pmcid'])
                            
                            if full_text:
                                # Store in database
                                await self._store_fulltext(doc_info['doc_id'], full_text, source='PMC')
                                
                                # Update raw_doc_texts for immediate use (ensure consistent string keys)
                                raw_doc_texts[str(doc_info['doc_id'])] = full_text
                                
                                logger.info(f"✅ Retrieved {len(full_text)} characters for PMID {doc_info['pmid']}")
                            else:
                                logger.warning(f"❌ Failed to retrieve full text for PMID {doc_info['pmid']}")
                                
                        except Exception as e:
                            logger.error(f"Error retrieving full text for PMID {doc_info['pmid']}: {e}")
                    
                    # Small delay between batches to be respectful to PMC
                    if i + batch_size < len(documents_to_process):
                        await asyncio.sleep(1)
                
                logger.info(f"Full text retrieval completed for {len(documents_to_process)} documents")
            
        except Exception as e:
            logger.error(f"Error in full text retrieval: {e}")
    
    async def _store_fulltext(self, doc_id: int, full_text: str, source: str) -> bool:
        """
        Store full text in the database.
        
        Args:
            doc_id: Document ID
            full_text: Full text content
            source: Source of the text (PMC, Unpaywall, etc.)
            
        Returns:
            True if stored successfully, False otherwise
        """
        try:
            from ncfd.db.session import session_scope
            from ncfd.db.models import DocumentText
            
            with session_scope() as session:
                # Check if DocumentText record exists
                doc_text = session.query(DocumentText).filter(DocumentText.doc_id == doc_id).first()
                
                if doc_text:
                    # Update existing record
                    doc_text.fulltext_text = full_text
                    doc_text.fulltext_source = source
                    doc_text.fulltext_retrieved_at = datetime.now(timezone.utc)
                else:
                    # Create new record
                    doc_text = DocumentText(
                        doc_id=doc_id,
                        fulltext_text=full_text,
                        fulltext_source=source,
                        fulltext_retrieved_at=datetime.now(timezone.utc)
                    )
                    session.add(doc_text)
                
                session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error storing full text for doc_id {doc_id}: {e}")
            return False
    
    async def _save_pattern_detection_to_db(self, pattern_detection: Any, trial_id: str) -> bool:
        """Save pattern detection to database."""
        try:
            from ncfd.db.session import session_scope
            from sqlalchemy import text
            
            with session_scope() as session:
                # Insert pattern detection into database
                import json
                session.execute(text("""
                    INSERT INTO pattern_detections (
                        trial_id, run_id, family_id, pattern_id, severity, 
                        confidence, rationale, evidence_spans, detected_at, created_at
                    ) VALUES (
                        :trial_id, :run_id, :family_id, :pattern_id, :severity,
                        :confidence, :rationale, :evidence_spans, NOW(), NOW()
                    )
                """), {
                    'trial_id': int(trial_id),
                    'run_id': "pattern_families_run",
                    'family_id': pattern_detection.family_id,
                    'pattern_id': pattern_detection.pattern_id,
                    'severity': pattern_detection.severity.value,  # SeverityLevel enum value (0-3)
                    'confidence': pattern_detection.confidence,
                    'rationale': pattern_detection.rationale,
                    'evidence_spans': json.dumps(pattern_detection.evidence_spans) if pattern_detection.evidence_spans else None
                })
                session.commit()
                logger.info(f"Pattern detection saved to database for trial_id: {trial_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error saving pattern detection: {e}")
            return False
    
