"""
Retriever Worker

Document retrieval and triage worker for finding high-quality evidence spans.
"""

from typing import Any, Dict, List, Optional
from .base_worker import BaseWorker, WorkerResult
from ..models import DocumentCard, EvidenceSpan
from ...utils.study_card_utils import generate_span_id, validate_span_coordinates


class Retriever(BaseWorker):
    """Worker for document retrieval and evidence span triage."""
    
    def __init__(self, max_span_length: int = 400, min_confidence: float = 0.7):
        super().__init__("Retriever", "1.0.0")
        self.max_span_length = max_span_length
        self.min_confidence = min_confidence
        
    def _validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate inputs for Retriever."""
        required_keys = ["trial_context"]
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs["trial_context"], dict):
            return False
            
        return True
    
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Process inputs to retrieve documents and create evidence spans."""
        try:
            trial_context = inputs["trial_context"]
            date_window = inputs.get("date_window", "2020-2024")
            
            # Retrieve documents based on trial context
            document_cards = self._retrieve_documents(trial_context, date_window)
            
            # Extract evidence spans from documents
            evidence_spans = self._extract_evidence_spans(document_cards)
            
            # Filter and quality-check spans
            filtered_spans = self._filter_spans(evidence_spans)
            
            # Add provenance
            for doc_card in document_cards:
                doc_card = self._add_provenance(doc_card, inputs)
            
            for span in filtered_spans:
                span = self._add_provenance(span, inputs)
            
            return WorkerResult(
                success=True,
                output={
                    "document_cards": document_cards,
                    "evidence_spans": filtered_spans
                },
                metadata={
                    "documents_retrieved": len(document_cards),
                    "spans_extracted": len(filtered_spans),
                    "date_window": date_window
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Retriever failed: {str(e)}"
            )
    
    def _retrieve_documents(self, trial_context: Dict[str, Any], 
                           date_window: str) -> List[DocumentCard]:
        """Retrieve relevant documents based on trial context."""
        documents = []
        
        # Extract key information from trial context
        disease = trial_context.get("disease", "")
        intervention = trial_context.get("intervention", "")
        study_type = trial_context.get("study_type", "")
        
        # This would integrate with actual document retrieval systems
        # For now, create mock documents based on context
        
        if disease and intervention:
            # Create a mock document card
            doc_card = DocumentCard(
                doc_id=f"ctgov:{trial_context.get('trial_id', 'NCT12345')}",
                doc_type="Paper",
                title=f"Study of {intervention} in {disease}",
                year=2023
            )
            
            # Add metadata
            doc_card.disease = disease
            doc_card.intervention = intervention
            doc_card.study_type = study_type or "RCT"
            doc_card.venue = "Clinical Trial"
            
            # Add fulltext references
            doc_card.add_fulltext_ref(1, 0, 500, "text")
            doc_card.add_fulltext_ref(2, 0, 600, "text")
            doc_card.add_fulltext_ref(3, 0, 400, "text")
            
            documents.append(doc_card)
        
        return documents
    
    def _extract_evidence_spans(self, document_cards: List[DocumentCard]) -> List[EvidenceSpan]:
        """Extract evidence spans from documents."""
        spans = []
        
        for doc_card in document_cards:
            # Extract spans from each document
            doc_spans = self._extract_spans_from_document(doc_card)
            spans.extend(doc_spans)
        
        return spans
    
    def _extract_spans_from_document(self, doc_card: DocumentCard) -> List[EvidenceSpan]:
        """Extract evidence spans from a single document."""
        spans = []
        
        # This would integrate with actual text extraction systems
        # For now, create mock spans based on fulltext references
        
        for ref in doc_card.fulltext_refs:
            # Create spans for different sections
            section_spans = self._create_section_spans(doc_card.doc_id, ref)
            spans.extend(section_spans)
        
        return spans
    
    def _create_section_spans(self, doc_id: str, ref: Dict[str, Any]) -> List[EvidenceSpan]:
        """Create evidence spans for different sections of a document."""
        spans = []
        page = ref["page"]
        
        # Create spans for different sections
        sections = [
            ("Methods", 0.8),
            ("Results", 0.9),
            ("Abstract", 0.7),
            ("Introduction", 0.6)
        ]
        
        for section_name, confidence in sections:
            # Mock quote - in practice this would be extracted text
            quote = f"This is a {section_name.lower()} section discussing the study methodology and results."
            
            # Ensure quote is within length limit
            if len(quote) > self.max_span_length:
                quote = quote[:self.max_span_length-3] + "..."
            
            # Create span ID with correct end position
            span_id = generate_span_id(doc_id, section_name, 0, len(quote), page)
            
            span = EvidenceSpan(
                span_id=span_id,
                doc_id=doc_id,
                page=page,
                char_start=0,
                char_end=len(quote),
                quote=quote,
                section=section_name,
                confidence=confidence
            )
            
            spans.append(span)
        
        return spans
    
    def _filter_spans(self, spans: List[EvidenceSpan]) -> List[EvidenceSpan]:
        """Filter spans based on quality criteria."""
        filtered = []
        
        for span in spans:
            # Check confidence threshold
            if span.confidence < self.min_confidence:
                continue
            
            # Check span length
            if len(span.quote) > self.max_span_length:
                continue
            
            # Check span coordinates
            if not validate_span_coordinates(span.page, span.char_start, span.char_end):
                continue
            
            # Check for low-quality indicators
            if self._is_low_quality_span(span):
                continue
            
            filtered.append(span)
        
        return filtered
    
    def _is_low_quality_span(self, span: EvidenceSpan) -> bool:
        """Check if a span is low quality."""
        text = span.quote.lower()
        
        # Check for common low-quality indicators
        low_quality_indicators = [
            "page", "figure", "table", "reference", "citation",
            "supplementary", "appendix", "footnote", "header", "footer"
        ]
        
        for indicator in low_quality_indicators:
            if indicator in text:
                return True
        
        # Check for very short spans
        if len(span.quote.strip()) < 20:
            return True
        
        # Check for spans with mostly numbers/symbols
        alphanumeric_chars = sum(1 for c in span.quote if c.isalnum())
        if alphanumeric_chars / len(span.quote) < 0.3:
            return True
        
        return False
    
    def get_retrieval_stats(self) -> Dict[str, Any]:
        """Get retrieval-specific statistics."""
        base_stats = self.get_stats()
        base_stats.update({
            "max_span_length": self.max_span_length,
            "min_confidence": self.min_confidence
        })
        return base_stats
