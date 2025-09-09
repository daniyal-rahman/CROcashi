"""
Direct Study Card Pipeline - LLM-First Architecture

Simplified pipeline that directly generates cards with evidence quotes,
then backtraces those quotes to spans.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from ..extract.workers.retriever_factory import build_retriever
from ..extract.workers.provenance_backtracer import ProvenanceBacktracer
from ..extract.workers.llm.llm_method_card_generator import LLMMethodCardGenerator
from ..extract.workers.llm.llm_results_factsheet_generator import LLMResultsFactsheetGenerator
from ..extract.workers.llm.llm_gate_assessment_generator import LLMGateAssessmentGenerator
from ..extract.models import (
    DocumentCard, EvidenceSpan, MethodCard, ResultsFactsheet, GateAssessment
)

logger = logging.getLogger(__name__)


@dataclass
class DirectStudyCardResult:
    """Result of direct study card pipeline execution."""
    trial_id: str
    success: bool
    start_time: datetime
    end_time: datetime
    processing_time_seconds: float = field(init=False, default=0.0)
    
    # Pipeline outputs
    document_cards: List[DocumentCard] = field(default_factory=list)
    evidence_spans: List[EvidenceSpan] = field(default_factory=list)
    method_card: Optional[MethodCard] = None
    results_factsheet: Optional[ResultsFactsheet] = None
    gate_assessments: List[GateAssessment] = field(default_factory=list)
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class DirectStudyCardPipeline:
    """Simplified study card pipeline with direct LLM card generation."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the direct study card pipeline.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.retriever = build_retriever(self.config)
        self.provenance_backtracer = ProvenanceBacktracer()
        
        # Direct LLM generators
        self.method_generator = LLMMethodCardGenerator()
        self.results_generator = LLMResultsFactsheetGenerator()
        self.gate_generator = LLMGateAssessmentGenerator()
        
        # Quality gate configuration
        self.min_documents = self.config.get('min_documents', 1)
        self.min_evidence_spans = self.config.get('min_evidence_spans', 3)
        self.require_method = self.config.get('require_method', True)
        self.require_results = self.config.get('require_results', True)
        self.require_gates = self.config.get('require_gates', True)
    
    async def execute(self, trial_id: str, trial_context: Dict[str, Any]) -> DirectStudyCardResult:
        """Execute the direct study card pipeline."""
        start_time = datetime.now(timezone.utc)
        result = DirectStudyCardResult(
            trial_id=trial_id,
            success=False,
            start_time=start_time,
            end_time=start_time
        )
        
        try:
            logger.info(f"Starting direct study card pipeline for trial {trial_id}")
            
            # Stage 1: Document retrieval
            logger.info("Stage 1: Document retrieval")
            retrieval_result = self._execute_retrieval(trial_context)
            if not retrieval_result.success:
                result.errors.append(f"Document retrieval failed: {retrieval_result.error_message}")
                return result
            
            result.document_cards = retrieval_result.output.get("document_cards", [])
            raw_doc_texts = retrieval_result.output.get("raw_doc_texts", {})
            
            logger.info(f"Retrieved {len(result.document_cards)} documents")
            
            if len(result.document_cards) < self.min_documents:
                result.errors.append(f"Insufficient documents: {len(result.document_cards)} < {self.min_documents}")
                return result
            
            # Stage 2: Direct card generation with evidence quotes
            logger.info("Stage 2: Direct card generation")
            all_quotes = []
            
            for doc_card in result.document_cards:
                doc_text = raw_doc_texts.get(doc_card.doc_id, "")
                if not doc_text:
                    result.warnings.append(f"No text available for document {doc_card.doc_id}")
                    continue
                
                # Generate method card
                if self.require_method:
                    method_result = await self.method_generator.process({
                        "raw_doc_text": doc_text,
                        "doc_id": doc_card.doc_id,
                        "trial_context": trial_context
                    })
                    
                    if method_result["success"] and method_result["method_card"]:
                        result.method_card = method_result["method_card"]
                        # Collect quotes for backtracing
                        for field_quote in method_result.get("field_quotes", []):
                            all_quotes.append({
                                "doc_id": doc_card.doc_id,
                                "text": field_quote.evidence_quote,
                                "field": f"method_{field_quote.field_name}",
                                "confidence": field_quote.confidence
                            })
                
                # Generate results factsheet
                if self.require_results:
                    results_result = await self.results_generator.process({
                        "raw_doc_text": doc_text,
                        "doc_id": doc_card.doc_id,
                        "trial_context": trial_context
                    })
                    
                    if results_result["success"] and results_result["results_factsheet"]:
                        result.results_factsheet = results_result["results_factsheet"]
                        # Collect quotes for backtracing
                        for field_quote in results_result.get("field_quotes", []):
                            all_quotes.append({
                                "doc_id": doc_card.doc_id,
                                "text": field_quote.evidence_quote,
                                "field": f"results_{field_quote.field_name}",
                                "confidence": field_quote.confidence
                            })
                
                # Generate gate assessments
                if self.require_gates:
                    gate_result = await self.gate_generator.process({
                        "raw_doc_text": doc_text,
                        "doc_id": doc_card.doc_id,
                        "trial_context": trial_context
                    })
                    
                    if gate_result["success"] and gate_result["gate_assessments"]:
                        result.gate_assessments.extend(gate_result["gate_assessments"])
                        # Collect quotes for backtracing
                        for field_quote in gate_result.get("field_quotes", []):
                            all_quotes.append({
                                "doc_id": doc_card.doc_id,
                                "text": field_quote.evidence_quote,
                                "field": f"gate_{field_quote.field_name}",
                                "confidence": field_quote.confidence
                            })
            
            logger.info(f"Generated {len(all_quotes)} evidence quotes")
            
            # Stage 3: Backtrace quotes to evidence spans
            logger.info("Stage 3: Backtrace quotes to evidence spans")
            all_evidence_spans = []
            
            for doc_card in result.document_cards:
                doc_text = raw_doc_texts.get(doc_card.doc_id, "")
                if not doc_text:
                    continue
                
                # Filter quotes for this document
                doc_quotes = [q for q in all_quotes if q.get("doc_id") == doc_card.doc_id]
                quote_texts = [q.get("text", "") for q in doc_quotes]
                
                # Backtrace to spans
                spans = self.provenance_backtracer.backtrace_quotes_to_spans(
                    quotes=quote_texts,
                    raw_doc_text=doc_text,
                    doc_id=doc_card.doc_id
                )
                all_evidence_spans.extend(spans)
            
            result.evidence_spans = all_evidence_spans
            logger.info(f"Backtraced {len(result.evidence_spans)} evidence spans")
            
            # Stage 4: Quality gate validation
            logger.info("Stage 4: Quality gate validation")
            is_valid, quality_errors = self._validate_quality(result)
            
            if not is_valid:
                result.errors.extend([f"Quality gate: {error}" for error in quality_errors])
                result.success = False
            else:
                result.success = True
            
            result.end_time = datetime.now(timezone.utc)
            result.processing_time_seconds = (result.end_time - result.start_time).total_seconds()
            
            logger.info(f"Direct study card pipeline completed for trial {trial_id}")
            logger.info(f"Generated: {len(result.document_cards)} docs, {len(result.evidence_spans)} spans")
            if result.method_card:
                logger.info("Method card generated")
            if result.results_factsheet:
                logger.info("Results factsheet generated")
            if result.gate_assessments:
                logger.info(f"{len(result.gate_assessments)} gate assessments generated")
            
            return result
            
        except Exception as e:
            logger.error(f"Direct study card pipeline failed for trial {trial_id}: {e}")
            result.errors.append(f"Pipeline execution failed: {str(e)}")
            result.end_time = datetime.now(timezone.utc)
            result.processing_time_seconds = (result.end_time - result.start_time).total_seconds()
            return result
    
    def _execute_retrieval(self, trial_context: Dict[str, Any]) -> Any:
        """Execute document retrieval stage."""
        inputs = {
            "trial_context": trial_context,
            "date_window": trial_context.get("date_window", "2020-2024")
        }
        return self.retriever.process(inputs)
    
    def _validate_quality(self, result: DirectStudyCardResult) -> Tuple[bool, List[str]]:
        """Validate study card quality."""
        errors = []
        
        # Check document count
        if len(result.document_cards) < self.min_documents:
            errors.append(f"Insufficient documents: {len(result.document_cards)} < {self.min_documents}")
        
        # Check evidence spans
        if len(result.evidence_spans) < self.min_evidence_spans:
            errors.append(f"Insufficient evidence spans: {len(result.evidence_spans)} < {self.min_evidence_spans}")
        
        # Check method card
        if self.require_method and not result.method_card:
            errors.append("Method card missing")
        
        # Check results factsheet
        if self.require_results and not result.results_factsheet:
            errors.append("Results factsheet missing")
        
        # Check gate assessments
        if self.require_gates and len(result.gate_assessments) == 0:
            errors.append("Gate assessments missing")
        
        return len(errors) == 0, errors
