"""
Provenance Backtracer Worker

Implements Phase B of the LLM-first, provenance-second architecture.
Finds exact spans that justify LLM-extracted values using fuzzy matching and retrieval.
"""

import re
import time
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import asdict
import logging

from .base_worker import BaseWorker, WorkerResult
from ..models import EvidenceSpan
from ..models.llm_extraction_draft import (
    LLMExtractionDraft, LLMResultsDraft, LLMMethodDraft, LLMClaimDraft,
    EvidenceKind, EvidenceStatus
)
from ...utils.study_card_utils import extract_numeric_value, normalize_units


class ProvenanceBacktracer(BaseWorker):
    """
    Worker for finding exact spans that justify LLM-extracted values.
    
    Implements Phase B of the LLM-first, provenance-second architecture:
    1. Candidate retrieval using BM25 and fuzzy matching
    2. Span alignment and scoring
    3. Provenance attachment to draft artifacts
    """
    
    def __init__(self, 
                 bm25_topk: int = 20,
                 fuzzy_threshold: float = 0.86,
                 numeric_strict: bool = True,
                 section_bonus: float = 0.1,
                 allow_table_only: bool = True):
        super().__init__("ProvenanceBacktracer", "1.0.0")
        
        self.bm25_topk = bm25_topk
        self.fuzzy_threshold = fuzzy_threshold
        self.numeric_strict = numeric_strict
        self.section_bonus = section_bonus
        self.allow_table_only = allow_table_only
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            h = logging.StreamHandler()
            fmt = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
            h.setFormatter(fmt)
            self.logger.addHandler(h)
        self.logger.setLevel(logging.INFO)
        
        # Fuzzy matching patterns
        self.numeric_patterns = {
            'percentage': r'(\d+\.?\d*)\s*%',
            'fraction': r'(\d+)/(\d+)',
            'decimal': r'(\d+\.?\d*)',
            'integer': r'(\d+)',
            'units': r'(weeks?|months?|years?|days?)'
        }
        
        # OCR noise patterns
        self.ocr_noise_map = {
            'l': '1', 'I': '1', 'O': '0', 'o': '0',
            'S': '5', 's': '5', 'Z': '2', 'z': '2',
            'B': '8', 'G': '6', 'g': '9'
        }

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required fields."""
        required_keys = ['llm_extraction_draft', 'raw_doc_text']
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs['llm_extraction_draft'], LLMExtractionDraft):
            return False
            
        if not isinstance(inputs['raw_doc_text'], str):
            return False
            
        return True

    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process LLM extraction draft to attach provenance spans.
        
        Args:
            inputs: Dict containing:
                - llm_extraction_draft: LLMExtractionDraft - Draft artifacts with verbatim quotes
                - raw_doc_text: str - Raw document text for span search
                - evidence_spans: List[EvidenceSpan] - Pre-existing spans (optional)
                
        Returns:
            WorkerResult containing LLMExtractionDraft with attached spans
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required llm_extraction_draft or raw_doc_text",
                    output={}
                )
            
            llm_draft = inputs['llm_extraction_draft']
            raw_doc_text = inputs['raw_doc_text']
            evidence_spans = inputs.get('evidence_spans', [])
            
            start_time = time.time()
            self.logger.info(f"Processing provenance backtrace for doc_id: {llm_draft.doc_id}")
            
            # Process each draft artifact type
            if llm_draft.results_draft:
                self._backtrace_results(llm_draft.results_draft, raw_doc_text, evidence_spans)
            
            if llm_draft.method_draft:
                self._backtrace_methods(llm_draft.method_draft, raw_doc_text, evidence_spans)
            
            if llm_draft.claims_draft:
                self._backtrace_claims(llm_draft.claims_draft, raw_doc_text, evidence_spans)
            
            # Update extraction timestamp
            llm_draft.extraction_timestamp = time.time()
            
            return WorkerResult(
                success=True,
                output={'llm_extraction_draft': llm_draft},
                execution_time=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Provenance backtrace failed: {str(e)}")
            return WorkerResult(
                success=False,
                error_message=f"Provenance backtrace failed: {str(e)}",
                output={}
            )

    def _backtrace_results(self, results_draft: LLMResultsDraft, 
                          raw_doc_text: str, evidence_spans: List[EvidenceSpan]):
        """Backtrace results to find supporting spans."""
        self.logger.info(f"Backtracing {len(results_draft.results)} results")
        
        for i, result in enumerate(results_draft.results):
            verbatim_quote = results_draft.verbatim_quotes[i]
            evidence_kind = results_draft.evidence_kinds[i]
            section_hint = results_draft.section_hints[i]
            table_hint = results_draft.table_hints[i]
            
            # Find supporting span
            span_id = self._find_supporting_span(
                verbatim_quote=verbatim_quote,
                field_name=result.get('metric', ''),
                field_value=result.get('value'),
                evidence_kind=evidence_kind,
                section_hint=section_hint,
                table_hint=table_hint,
                raw_doc_text=raw_doc_text,
                evidence_spans=evidence_spans
            )
            
            if span_id:
                results_draft.span_ids[i] = span_id
                results_draft.provenance_status[i] = "resolved"
            else:
                results_draft.provenance_status[i] = "unresolved"
                # Lower confidence for unresolved provenance
                results_draft.confidence_llm[i] = max(0.2, results_draft.confidence_llm[i] - 0.4)

    def _backtrace_methods(self, method_draft: LLMMethodDraft,
                         raw_doc_text: str, evidence_spans: List[EvidenceSpan]):
        """Backtrace methods to find supporting spans."""
        self.logger.info(f"Backtracing {len(method_draft.field_names)} method fields")
        
        for i, field_name in enumerate(method_draft.field_names):
            verbatim_quote = method_draft.verbatim_quotes[i]
            field_value = method_draft.normalized_values[i]
            evidence_kind = method_draft.evidence_kinds[i]
            section_hint = method_draft.section_hints[i]
            
            # Find supporting span
            span_id = self._find_supporting_span(
                verbatim_quote=verbatim_quote,
                field_name=field_name,
                field_value=field_value,
                evidence_kind=evidence_kind,
                section_hint=section_hint,
                table_hint=None,
                raw_doc_text=raw_doc_text,
                evidence_spans=evidence_spans
            )
            
            if span_id:
                method_draft.span_ids[i] = span_id
                method_draft.provenance_status[i] = "resolved"
            else:
                method_draft.provenance_status[i] = "unresolved"
                # Lower confidence for unresolved provenance
                method_draft.confidence_llm[i] = max(0.2, method_draft.confidence_llm[i] - 0.4)

    def _backtrace_claims(self, claims_draft: LLMClaimDraft,
                         raw_doc_text: str, evidence_spans: List[EvidenceSpan]):
        """Backtrace claims to find supporting spans."""
        self.logger.info(f"Backtracing {len(claims_draft.claim_types)} claims")
        
        for i, claim_type in enumerate(claims_draft.claim_types):
            verbatim_quote = claims_draft.verbatim_quotes[i]
            proposition = claims_draft.propositions[i]
            field_value = claims_draft.values[i]
            evidence_kind = claims_draft.evidence_kinds[i]
            section_hint = claims_draft.section_hints[i]
            
            # Find supporting span
            span_id = self._find_supporting_span(
                verbatim_quote=verbatim_quote,
                field_name=claim_type,
                field_value=field_value,
                evidence_kind=evidence_kind,
                section_hint=section_hint,
                table_hint=None,
                raw_doc_text=raw_doc_text,
                evidence_spans=evidence_spans
            )
            
            if span_id:
                claims_draft.span_ids[i] = span_id
                claims_draft.provenance_status[i] = "resolved"
            else:
                claims_draft.provenance_status[i] = "unresolved"
                # Lower confidence for unresolved provenance
                claims_draft.confidence_llm[i] = max(0.2, claims_draft.confidence_llm[i] - 0.4)

    def _find_supporting_span(self,
                            verbatim_quote: str,
                            field_name: str,
                            field_value: Any,
                            evidence_kind: EvidenceKind,
                            section_hint: str,
                            table_hint: Optional[str],
                            raw_doc_text: str,
                            evidence_spans: List[EvidenceSpan]) -> Optional[str]:
        """Find the best supporting span for a field/quote combination."""
        
        # Step 1: Candidate retrieval
        candidates = self._retrieve_candidates(
            verbatim_quote=verbatim_quote,
            field_name=field_name,
            field_value=field_value,
            evidence_kind=evidence_kind,
            section_hint=section_hint,
            table_hint=table_hint,
            raw_doc_text=raw_doc_text,
            evidence_spans=evidence_spans
        )
        
        if not candidates:
            return None
        
        # Step 2: Fuzzy alignment and scoring
        best_span_id = None
        best_score = 0.0
        
        for candidate in candidates:
            score = self._score_candidate(
                candidate=candidate,
                verbatim_quote=verbatim_quote,
                field_name=field_name,
                field_value=field_value,
                evidence_kind=evidence_kind,
                section_hint=section_hint,
                table_hint=table_hint
            )
            
            if score > best_score and score >= self.fuzzy_threshold:
                best_score = score
                best_span_id = candidate.get('span_id')
        
        return best_span_id

    def _retrieve_candidates(self,
                          verbatim_quote: str,
                          field_name: str,
                          field_value: Any,
                          evidence_kind: EvidenceKind,
                          section_hint: str,
                          table_hint: Optional[str],
                          raw_doc_text: str,
                          evidence_spans: List[EvidenceSpan]) -> List[Dict[str, Any]]:
        """Retrieve candidate spans using BM25 and fuzzy matching."""
        candidates = []
        
        # Build query from verbatim quote (preferred) or field name + value
        if verbatim_quote and len(verbatim_quote.strip()) > 0:
            query = verbatim_quote
        else:
            query = f"{field_name} {field_value}"
        
        # Normalize query for matching
        normalized_query = self._normalize_text(query)
        
        # Search in raw document text using sliding window approach
        window_size = 200  # characters
        step_size = 100    # characters
        
        for start in range(0, len(raw_doc_text), step_size):
            end = min(start + window_size, len(raw_doc_text))
            window_text = raw_doc_text[start:end]
            
            # Calculate BM25-like score
            bm25_score = self._calculate_bm25_score(normalized_query, window_text)
            
            # Calculate fuzzy match score
            fuzzy_score = self._calculate_fuzzy_score(normalized_query, window_text)
            
            # Calculate numeric overlap score
            numeric_score = self._calculate_numeric_overlap(field_value, window_text)
            
            # Calculate section bonus
            section_score = self._calculate_section_bonus(section_hint, window_text)
            
            # Combined score
            combined_score = (
                0.4 * bm25_score +
                0.3 * fuzzy_score +
                0.2 * numeric_score +
                0.1 * section_score
            )
            
            if combined_score > 0.3:  # Minimum threshold for candidates
                candidates.append({
                    'span_id': f"raw_text:{start}-{end}",
                    'text': window_text,
                    'start': start,
                    'end': end,
                    'bm25_score': bm25_score,
                    'fuzzy_score': fuzzy_score,
                    'numeric_score': numeric_score,
                    'section_score': section_score,
                    'combined_score': combined_score
                })
        
        # Also check pre-existing evidence spans
        for span in evidence_spans:
            span_score = self._calculate_span_score(
                span=span,
                verbatim_quote=verbatim_quote,
                field_name=field_name,
                field_value=field_value,
                evidence_kind=evidence_kind,
                section_hint=section_hint
            )
            
            if span_score > 0.3:
                candidates.append({
                    'span_id': span.span_id,
                    'text': span.quote,
                    'start': span.char_start,
                    'end': span.char_end,
                    'bm25_score': span_score,
                    'fuzzy_score': span_score,
                    'numeric_score': span_score,
                    'section_score': span_score,
                    'combined_score': span_score
                })
        
        # Sort by combined score and return top candidates
        candidates.sort(key=lambda x: x['combined_score'], reverse=True)
        return candidates[:self.bm25_topk]

    def _score_candidate(self,
                        candidate: Dict[str, Any],
                        verbatim_quote: str,
                        field_name: str,
                        field_value: Any,
                        evidence_kind: EvidenceKind,
                        section_hint: str,
                        table_hint: Optional[str]) -> float:
        """Score a candidate span for alignment quality."""
        
        candidate_text = candidate['text']
        
        # Fuzzy alignment score
        if verbatim_quote and len(verbatim_quote.strip()) > 0:
            alignment_score = self._calculate_fuzzy_alignment(verbatim_quote, candidate_text)
        else:
            # Fallback to field name + value matching
            alignment_score = self._calculate_field_alignment(field_name, field_value, candidate_text)
        
        # Numeric overlap check (strict mode)
        if self.numeric_strict and field_value is not None:
            numeric_overlap = self._check_numeric_overlap(field_value, candidate_text)
            if not numeric_overlap:
                return 0.0  # Hard fail if numeric values don't match
        
        # Evidence kind bonus
        kind_bonus = 0.0
        if evidence_kind == EvidenceKind.TABLE and 'table' in candidate_text.lower():
            kind_bonus = 0.1
        elif evidence_kind == EvidenceKind.TEXT and 'table' not in candidate_text.lower():
            kind_bonus = 0.05
        
        # Section hint bonus
        section_bonus = 0.0
        if section_hint and section_hint.lower() in candidate_text.lower():
            section_bonus = self.section_bonus
        
        # Final score
        final_score = alignment_score + kind_bonus + section_bonus
        return min(1.0, final_score)

    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching using shared TextNormalizer."""
        from ..utils.text_normalization import TextNormalizer
        return TextNormalizer.normalize_text(text, aggressive=True)

    def _calculate_bm25_score(self, query: str, text: str) -> float:
        """Calculate BM25-like score for query-text matching."""
        if not query or not text:
            return 0.0
        
        query_tokens = set(query.split())
        text_tokens = text.split()
        
        if not query_tokens or not text_tokens:
            return 0.0
        
        # Simple term frequency calculation
        matches = 0
        for query_token in query_tokens:
            if query_token in text_tokens:
                matches += 1
        
        # Normalize by query length
        return matches / len(query_tokens)

    def _calculate_fuzzy_score(self, query: str, text: str) -> float:
        """Calculate fuzzy matching score."""
        if not query or not text:
            return 0.0
        
        # Simple substring matching with normalization
        normalized_query = self._normalize_text(query)
        normalized_text = self._normalize_text(text)
        
        if normalized_query in normalized_text:
            return 1.0
        
        # Partial matching
        query_words = normalized_query.split()
        text_words = normalized_text.split()
        
        matches = 0
        for query_word in query_words:
            if any(query_word in text_word or text_word in query_word for text_word in text_words):
                matches += 1
        
        return matches / len(query_words) if query_words else 0.0

    def _calculate_numeric_overlap(self, field_value: Any, text: str) -> float:
        """Calculate numeric overlap between field value and text."""
        if field_value is None:
            return 0.0
        
        # Extract numeric values from text
        text_numbers = self._extract_numbers_from_text(text)
        
        if not text_numbers:
            return 0.0
        
        # Check if field value appears in text numbers
        field_numbers = self._extract_numbers_from_value(field_value)
        
        matches = 0
        for field_num in field_numbers:
            for text_num in text_numbers:
                if self._numbers_match(field_num, text_num):
                    matches += 1
        
        return matches / len(field_numbers) if field_numbers else 0.0

    def _extract_numbers_from_text(self, text: str) -> List[float]:
        """Extract all numeric values from text using shared TextNormalizer."""
        from ..utils.text_normalization import TextNormalizer
        return TextNormalizer.extract_numbers_from_text(text)

    def _extract_numbers_from_value(self, value: Any) -> List[float]:
        """Extract numeric values from field value."""
        if isinstance(value, (int, float)):
            return [float(value)]
        elif isinstance(value, str):
            return self._extract_numbers_from_text(value)
        else:
            return []

    def _numbers_match(self, num1: float, num2: float, tolerance: float = 0.01) -> bool:
        """Check if two numbers match within tolerance."""
        return abs(num1 - num2) <= tolerance

    def _calculate_section_bonus(self, section_hint: str, text: str) -> float:
        """Calculate bonus for section hint matching."""
        if not section_hint:
            return 0.0
        
        section_hint_lower = section_hint.lower()
        text_lower = text.lower()
        
        if section_hint_lower in text_lower:
            return 0.1
        elif any(word in text_lower for word in section_hint_lower.split()):
            return 0.05
        
        return 0.0

    def _calculate_span_score(self,
                             span: EvidenceSpan,
                             verbatim_quote: str,
                             field_name: str,
                             field_value: Any,
                             evidence_kind: EvidenceKind,
                             section_hint: str) -> float:
        """Calculate score for pre-existing evidence span."""
        if not span.quote:
            return 0.0
        
        # Use the same scoring logic as for raw text candidates
        return self._calculate_fuzzy_score(verbatim_quote or f"{field_name} {field_value}", span.quote)

    def _calculate_fuzzy_alignment(self, verbatim_quote: str, text: str) -> float:
        """Calculate fuzzy alignment between verbatim quote and text."""
        return self._calculate_fuzzy_score(verbatim_quote, text)

    def _calculate_field_alignment(self, field_name: str, field_value: Any, text: str) -> float:
        """Calculate alignment for field name and value."""
        query = f"{field_name} {field_value}"
        return self._calculate_fuzzy_score(query, text)

    def _check_numeric_overlap(self, field_value: Any, text: str) -> bool:
        """Check if numeric values overlap (strict mode)."""
        if field_value is None:
            return True  # Non-numeric values pass
        
        field_numbers = self._extract_numbers_from_value(field_value)
        text_numbers = self._extract_numbers_from_text(text)
        
        if not field_numbers:
            return True  # No numeric values to check
        
        # Check if any field number appears in text
        for field_num in field_numbers:
            if any(self._numbers_match(field_num, text_num) for text_num in text_numbers):
                return True
        
        return False
