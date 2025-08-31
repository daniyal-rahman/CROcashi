"""
Fuzzy Aligner Worker

Aligns candidate quotes to BaseSpans or creates DerivedSpans when exact matches aren't found.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher
try:
    from Levenshtein import ratio as levenshtein_ratio
except ImportError:
    # Fallback if python-Levenshtein is not available
    def levenshtein_ratio(s1, s2):
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        return 1.0 - (self._levenshtein_distance(s1, s2) / max(len(s1), len(s2)))
    
    def _levenshtein_distance(s1, s2):
        if len(s1) < len(s2):
            return _levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

from ..workers.base_worker import BaseWorker, WorkerResult
from ...db.models import BaseSpan, DerivedSpan, Document
from ...db.session import get_session


@dataclass
class AlignmentConfig:
    """Configuration for fuzzy alignment."""
    similarity_threshold: float = 0.85
    use_levenshtein: bool = True
    use_sequence_matcher: bool = True
    use_token_set: bool = True
    normalize_text: bool = True
    preserve_case: bool = False
    max_derived_span_length: int = 1000


class FuzzyAligner(BaseWorker):
    """Worker for fuzzy alignment of quotes to spans."""
    
    def __init__(self, config: Optional[AlignmentConfig] = None):
        super().__init__(name="FuzzyAligner", version="1.0.0")
        self.config = config or AlignmentConfig()
        
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """Align candidate quotes to spans."""
        doc_id = inputs.get("doc_id")
        quotes = inputs.get("quotes", [])
        
        if not doc_id:
            return WorkerResult(
                success=False,
                output=None,
                error_message="doc_id is required"
            )
        
        if not quotes:
            return WorkerResult(
                success=False,
                output=None,
                error_message="quotes list is required"
            )
        
        try:
            with get_session() as session:
                # Get document and its spans
                document = session.query(Document).filter(Document.doc_id == doc_id).first()
                if not document:
                    return WorkerResult(
                        success=False,
                        output=None,
                        error_message=f"Document {doc_id} not found"
                    )
                
                # Get all base spans for the document
                base_spans = session.query(BaseSpan).filter(BaseSpan.doc_id == doc_id).all()
                
                # Align each quote
                alignment_results = []
                for quote in quotes:
                    result = self._align_quote(session, quote, base_spans, doc_id)
                    alignment_results.append(result)
                
                return WorkerResult(
                    success=True,
                    output={
                        "alignments": alignment_results,
                        "total_quotes": len(quotes),
                        "successful_alignments": sum(1 for r in alignment_results if r['aligned']),
                        "failed_alignments": sum(1 for r in alignment_results if not r['aligned'])
                    },
                    metadata={
                        "doc_id": doc_id,
                        "config": self.config.__dict__
                    }
                )
                
        except Exception as e:
            return WorkerResult(
                success=False,
                output=None,
                error_message=f"Error aligning quotes for document {doc_id}: {str(e)}"
            )
    
    def _align_quote(self, session, quote: str, base_spans: List[BaseSpan], doc_id: int) -> Dict[str, Any]:
        """Align a single quote to spans."""
        # Normalize quote
        normalized_quote = self._normalize_text(quote)
        
        # Try to find exact match in base spans first
        exact_match = self._find_exact_match(normalized_quote, base_spans)
        if exact_match:
            return {
                'quote': quote,
                'aligned': True,
                'match_type': 'exact',
                'span_id': exact_match.span_id,
                'similarity_score': 1.0,
                'derived_span_id': None
            }
        
        # Try fuzzy matching
        best_match = self._find_fuzzy_match(normalized_quote, base_spans)
        if best_match and best_match['similarity'] >= self.config.similarity_threshold:
            # Check if quote is contained within the matched span
            if self._is_contained_within(normalized_quote, best_match['span']):
                return {
                    'quote': quote,
                    'aligned': True,
                    'match_type': 'contained',
                    'span_id': best_match['span'].span_id,
                    'similarity_score': best_match['similarity'],
                    'derived_span_id': None
                }
            else:
                # Create derived span
                derived_span = self._create_derived_span(
                    session, quote, normalized_quote, best_match['span'], doc_id
                )
                return {
                    'quote': quote,
                    'aligned': True,
                    'match_type': 'derived',
                    'span_id': best_match['span'].span_id,
                    'similarity_score': best_match['similarity'],
                    'derived_span_id': derived_span.derived_id
                }
        
        # No match found
        return {
            'quote': quote,
            'aligned': False,
            'match_type': 'none',
            'span_id': None,
            'similarity_score': 0.0,
            'derived_span_id': None,
            'error': 'No match found above similarity threshold'
        }
    
    def _find_exact_match(self, normalized_quote: str, base_spans: List[BaseSpan]) -> Optional[BaseSpan]:
        """Find exact text match in base spans."""
        for span in base_spans:
            normalized_span_text = self._normalize_text(span.text)
            if normalized_quote == normalized_span_text:
                return span
        return None
    
    def _find_fuzzy_match(self, normalized_quote: str, base_spans: List[BaseSpan]) -> Optional[Dict[str, Any]]:
        """Find best fuzzy match among base spans."""
        best_match = None
        best_similarity = 0.0
        
        for span in base_spans:
            normalized_span_text = self._normalize_text(span.text)
            
            # Calculate similarity using multiple methods
            similarities = []
            
            if self.config.use_levenshtein:
                lev_sim = levenshtein_ratio(normalized_quote, normalized_span_text)
                similarities.append(lev_sim)
            
            if self.config.use_sequence_matcher:
                seq_sim = SequenceMatcher(None, normalized_quote, normalized_span_text).ratio()
                similarities.append(seq_sim)
            
            if self.config.use_token_set:
                token_sim = self._token_set_similarity(normalized_quote, normalized_span_text)
                similarities.append(token_sim)
            
            # Use average similarity
            if similarities:
                avg_similarity = sum(similarities) / len(similarities)
                
                if avg_similarity > best_similarity:
                    best_similarity = avg_similarity
                    best_match = {
                        'span': span,
                        'similarity': avg_similarity,
                        'method': 'combined'
                    }
        
        return best_match if best_similarity > 0 else None
    
    def _token_set_similarity(self, text1: str, text2: str) -> float:
        """Calculate token set similarity between two texts."""
        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())
        
        if not tokens1 and not tokens2:
            return 1.0
        if not tokens1 or not tokens2:
            return 0.0
        
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        
        return len(intersection) / len(union)
    
    def _is_contained_within(self, quote: str, span: BaseSpan) -> bool:
        """Check if quote is contained within the span text."""
        normalized_quote = self._normalize_text(quote)
        normalized_span_text = self._normalize_text(span.text)
        
        return normalized_quote in normalized_span_text
    
    def _create_derived_span(self, session, original_quote: str, normalized_quote: str, 
                            parent_span: BaseSpan, doc_id: int) -> DerivedSpan:
        """Create a derived span for a quote that doesn't exactly match any base span."""
        # Find the best position in the parent span's text
        parent_text = self._normalize_text(parent_span.text)
        quote_start = parent_text.find(normalized_quote)
        
        if quote_start != -1:
            # Quote found within parent span text
            char_start = parent_span.char_start + quote_start
            char_end = char_start + len(normalized_quote)
        else:
            # Quote not found, use approximate position
            # This is a fallback - in practice, we should have found it above
            char_start = parent_span.char_start
            char_end = min(char_start + len(normalized_quote), parent_span.char_end)
        
        # Create derived span
        derived_span = DerivedSpan(
            doc_id=doc_id,
            char_start=char_start,
            char_end=char_end,
            parent_span_ids=[parent_span.span_id],
            text=original_quote,
            similarity_score=0.85  # Default similarity for derived spans
        )
        
        # Save to database
        session.add(derived_span)
        session.commit()
        
        return derived_span
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        if not text:
            return ""
        
        normalized = text
        
        if self.config.normalize_text:
            # Remove extra whitespace
            normalized = re.sub(r'\s+', ' ', normalized)
            normalized = normalized.strip()
            
            # Remove punctuation (optional)
            # normalized = re.sub(r'[^\w\s]', '', normalized)
        
        if not self.config.preserve_case:
            normalized = normalized.lower()
        
        return normalized
    
    def align_single_quote(self, quote: str, doc_id: int) -> Dict[str, Any]:
        """Align a single quote (convenience method)."""
        return self.process({
            "doc_id": doc_id,
            "quotes": [quote]
        })
    
    def get_alignment_stats(self, doc_id: int) -> Dict[str, Any]:
        """Get alignment statistics for a document."""
        try:
            with get_session() as session:
                # Count base spans
                base_span_count = session.query(BaseSpan).filter(
                    BaseSpan.doc_id == doc_id
                ).count()
                
                # Count derived spans
                derived_span_count = session.query(DerivedSpan).filter(
                    DerivedSpan.doc_id == doc_id
                ).count()
                
                # Get span distribution by section
                section_counts = session.query(
                    BaseSpan.section,
                    func.count(BaseSpan.span_id)
                ).filter(
                    BaseSpan.doc_id == doc_id
                ).group_by(BaseSpan.section).all()
                
                return {
                    "doc_id": doc_id,
                    "base_spans": base_span_count,
                    "derived_spans": derived_span_count,
                    "total_spans": base_span_count + derived_span_count,
                    "section_distribution": dict(section_counts)
                }
                
        except Exception as e:
            return {
                "error": str(e)
            }
    
    def validate_alignment(self, quote: str, span_id: int, doc_id: int) -> bool:
        """Validate that a quote is properly aligned to a span."""
        try:
            with get_session() as session:
                # Check if span exists and belongs to document
                span = session.query(BaseSpan).filter(
                    BaseSpan.span_id == span_id,
                    BaseSpan.doc_id == doc_id
                ).first()
                
                if not span:
                    return False
                
                # Check if quote is contained within span text
                normalized_quote = self._normalize_text(quote)
                normalized_span_text = self._normalize_text(span.text)
                
                return normalized_quote in normalized_span_text
                
        except Exception:
            return False
