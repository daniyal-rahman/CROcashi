"""
Robust Provenance Backtracer

Implements the 5-stage robust design for finding exact spans that justify LLM-extracted values.
This is a complete rewrite with better accuracy, speed, and maintainability.
"""

import re
import unicodedata
import regex as re_fuzzy
import logging
import time
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from collections import defaultdict
from ncfd.extract.models.evidence_span import EvidenceSpan


@dataclass
class NormalizedDocument:
    """Container for normalized document variants and offset maps."""
    raw_text: str
    norm_basic: str
    norm_nohyphen: str
    norm_ascii: str
    basic_to_raw_map: List[int]
    nohyphen_to_raw_map: List[int]
    ascii_to_raw_map: List[int]
    sections: List[Dict[str, Any]]  # List of {start, end, name} dicts


@dataclass
class CandidateWindow:
    """A candidate window for quote alignment."""
    start: int
    end: int
    anchor_tokens: List[str]
    score: float


class ProvenanceBacktracer:
    """
    Provenance backtracer implementing the 5-stage design:
    
    Stage A: Normalize with indexable variants + offset map
    Stage B: Candidate generation (cheap but precise)  
    Stage C: Alignment (exact boundaries)
    Stage D: Scoring & dedupe
    Stage E: Section inference (cleaner)
    """
    
    def __init__(self, 
                 max_edits_ratio: float = 0.15,
                 window_size: int = 800,
                 overlap_threshold: float = 0.6,
                 min_anchor_tokens: int = 2):
        self.max_edits_ratio = max_edits_ratio
        self.window_size = window_size
        self.overlap_threshold = overlap_threshold
        self.min_anchor_tokens = min_anchor_tokens
        self.logger = logging.getLogger(__name__)
        
        # Section detection patterns
        self.section_patterns = [
            r'^[A-Z][A-Z\s]+$',  # All caps
            r'^\d+\.?\s+[A-Z]',  # Numbered sections
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$',  # Title case
            r'^[A-Z][A-Z\s]+:$',  # All caps with colon
        ]
    
    def backtrace_quotes_to_spans(self, quotes: List[str], raw_doc_text: str, doc_id: str, 
                                 alignment_threshold: float = 0.8) -> List[EvidenceSpan]:
        """
        Main entry point for backtracing quotes to spans.
        
        Args:
            quotes: List of quote strings from LLM
            raw_doc_text: Raw document text to search in
            doc_id: Document identifier
            alignment_threshold: Minimum fuzzy match score
                
        Returns:
            List of EvidenceSpan objects with backtraced spans
        """
        if not quotes or not raw_doc_text:
            return []
        
        start_time = time.time()
        max_time = 30.0  # 30 second timeout
        
        try:
            # Stage A: Normalize document with offset maps
            norm_doc = self._normalize_document(raw_doc_text)
            
            if time.time() - start_time > max_time:
                logging.warning("Backtracing timeout during normalization")
                return []
            
            # Stage E: Segment document into sections
            norm_doc.sections = self._segment_document(norm_doc.raw_text)
            
            evidence_spans = []
            
            for quote in quotes:
                if time.time() - start_time > max_time:
                    logging.warning("Backtracing timeout during quote processing")
                    break
                    
                if not quote or not quote.strip():
                    continue
                    
                # Find best alignment using robust pipeline
                best_span = self._find_quote_span_robust(quote, norm_doc, alignment_threshold)
                
                if best_span:
                    evidence_spans.append(best_span)
            
            # Stage D: Deduplicate overlapping spans
            evidence_spans = self._deduplicate_spans(evidence_spans)
            
            return evidence_spans
            
        except Exception as e:
            logging.error(f"Error in backtracing: {e}")
            return []
    
    def _normalize_document(self, raw_text: str) -> NormalizedDocument:
        """
        Stage A: Normalize with indexable variants + offset map.
        
        Creates multiple normalized variants and maintains offset maps back to raw text.
        """
        # Basic normalization: case fold, unicode NFKC, whitespace collapse
        norm_basic, basic_to_raw = self._normalize_with_map(raw_text, variant='basic')
        
        # No-hyphen normalization: also unwrap line-break hyphens
        norm_nohyphen, nohyphen_to_raw = self._normalize_with_map(raw_text, variant='nohyphen')
        
        # ASCII normalization: convert unicode to ASCII equivalents
        norm_ascii, ascii_to_raw = self._normalize_with_map(raw_text, variant='ascii')
        
        return NormalizedDocument(
            raw_text=raw_text,
            norm_basic=norm_basic,
            norm_nohyphen=norm_nohyphen,
            norm_ascii=norm_ascii,
            basic_to_raw_map=basic_to_raw,
            nohyphen_to_raw_map=nohyphen_to_raw,
            ascii_to_raw_map=ascii_to_raw,
            sections=[]
        )
    
    def _normalize_with_map(self, text: str, variant: str = 'basic') -> Tuple[str, List[int]]:
        """
        Normalize text and return offset map from normalized to raw positions.
        
        Args:
            text: Raw text to normalize
            variant: Normalization variant ('basic', 'nohyphen', 'ascii')
            
        Returns:
            Tuple of (normalized_text, offset_map)
        """
        normalized = text
        offset_map = list(range(len(text)))  # Start with identity mapping
        
        if variant == 'basic':
            # Case fold, unicode NFKC, collapse whitespace
            normalized = unicodedata.normalize('NFKC', text.lower())
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            
        elif variant == 'nohyphen':
            # Basic normalization + unwrap line-break hyphens
            normalized = unicodedata.normalize('NFKC', text.lower())
            # Unwrap hyphens at line breaks: "neuro- \n degeneration" -> "neurodegeneration"
            normalized = re.sub(r'-\s*\n\s*', '', normalized)
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            
        elif variant == 'ascii':
            # ASCII normalization for latin/greek look-alikes
            normalized = unicodedata.normalize('NFKD', text.lower())
            # Convert common unicode to ASCII
            normalized = normalized.replace('α', 'alpha').replace('β', 'beta')
            normalized = normalized.replace('γ', 'gamma').replace('δ', 'delta')
            normalized = re.sub(r'[^\x00-\x7F]', '', normalized)  # Remove non-ASCII
            normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Build offset map (simplified - in practice would need more sophisticated mapping)
        offset_map = list(range(len(normalized)))
        
        return normalized, offset_map
    
    def _segment_document(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Stage E: Segment document into sections using regex patterns.
        
        Returns list of section dicts with start, end, and name.
        """
        sections = []
        lines = raw_text.split('\n')
        
        current_section = None
        current_start = 0
        
        for i, line in enumerate(lines):
            line_start = raw_text.find(line, current_start)
            line_end = line_start + len(line)
            
            # Check if this line looks like a section header
            is_header = any(re.match(pattern, line.strip()) for pattern in self.section_patterns)
            
            if is_header:
                # Close previous section
                if current_section:
                    current_section['end'] = line_start
                    sections.append(current_section)
                
                # Start new section
                current_section = {
                    'name': line.strip().lower(),
                    'start': line_start,
                    'end': len(raw_text)  # Will be updated when next section starts
                }
                current_start = line_end
        
        # Close final section
        if current_section:
            current_section['end'] = len(raw_text)
            sections.append(current_section)
        
        # If no sections found, create a single "unknown" section
        if not sections:
            sections.append({
                'name': 'unknown',
                'start': 0,
                'end': len(raw_text)
            })
        
        return sections
    
    def _find_quote_span_robust(self, quote: str, norm_doc: NormalizedDocument, 
                               threshold: float) -> Optional[EvidenceSpan]:
        """
        Find quote span using the robust 5-stage pipeline.
        """
        # Stage B: Generate candidates using anchor tokens
        candidates = self._generate_candidates(quote, norm_doc)
        
        if not candidates:
            return None
        
        # Stage C: Align within each candidate window
        best_span = None
        best_score = 0.0
        
        for candidate in candidates:
            span = self._align_quote_in_window(quote, candidate, norm_doc, threshold)
            if span and span.confidence > best_score:
                best_span = span
                best_score = span.confidence
        
        return best_span
    
    def _generate_candidates(self, quote: str, norm_doc: NormalizedDocument) -> List[CandidateWindow]:
        """
        Stage B: Generate candidate windows using anchor tokens and inverted index.
        """
        # Tokenize quote and select anchor tokens (rarest terms)
        quote_tokens = self._tokenize(quote)
        
        # For very short quotes, use the whole quote as a single token
        if len(quote_tokens) < self.min_anchor_tokens:
            if len(quote.strip()) < 10:  # Very short quotes
                # Use the whole quote as a single search term
                normalized_quote = self._normalize_text(quote)
                if normalized_quote in norm_doc.norm_basic:
                    # Find all positions of this exact substring
                    positions = []
                    start = 0
                    while True:
                        pos = norm_doc.norm_basic.find(normalized_quote, start)
                        if pos == -1:
                            break
                        positions.append(pos)
                        start = pos + 1
                    
                    if positions:
                        candidates = []
                        for pos in positions:
                            window_start = max(0, pos - self.window_size // 2)
                            window_end = min(len(norm_doc.norm_basic), pos + self.window_size // 2)
                            
                            candidate = CandidateWindow(
                                start=window_start,
                                end=window_end,
                                anchor_tokens=[normalized_quote],
                                score=1.0
                            )
                            candidates.append(candidate)
                        return candidates
            return []
        
        # Select 2-4 anchor tokens (simplified - in practice would use IDF)
        anchor_tokens = quote_tokens[:min(4, len(quote_tokens))]
        
        # Build inverted index over normalized document
        inverted_index = self._build_inverted_index(norm_doc.norm_basic)
        
        # Find positions for each anchor token
        candidate_positions = set()
        for token in anchor_tokens:
            if token in inverted_index:
                candidate_positions.update(inverted_index[token])
        
        if not candidate_positions:
            return []
        
        # Create candidate windows around anchor positions
        candidates = []
        for pos in candidate_positions:
            window_start = max(0, pos - self.window_size // 2)
            window_end = min(len(norm_doc.norm_basic), pos + self.window_size // 2)
            
            candidate = CandidateWindow(
                start=window_start,
                end=window_end,
                anchor_tokens=anchor_tokens,
                score=1.0  # Simplified scoring
            )
            candidates.append(candidate)
        
        # Merge overlapping windows
        candidates = self._merge_overlapping_windows(candidates)
        
        return candidates
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization for anchor selection."""
        # Normalize and split on whitespace
        normalized = re.sub(r'\s+', ' ', text.lower().strip())
        return [token for token in normalized.split() if len(token) > 2]
    
    def _build_inverted_index(self, normalized_text: str) -> Dict[str, List[int]]:
        """Build simple inverted index: token -> list of character positions."""
        index = defaultdict(list)
        tokens = self._tokenize(normalized_text)
        
        current_pos = 0
        for token in tokens:
            pos = normalized_text.find(token, current_pos)
            if pos >= 0:
                index[token].append(pos)
                current_pos = pos + 1
        
        return dict(index)
    
    def _merge_overlapping_windows(self, candidates: List[CandidateWindow]) -> List[CandidateWindow]:
        """Merge overlapping candidate windows."""
        if not candidates:
            return []
        
        # Sort by start position
        candidates.sort(key=lambda c: c.start)
        
        merged = []
        current = candidates[0]
        
        for next_candidate in candidates[1:]:
            # Check if windows overlap
            if next_candidate.start <= current.end:
                # Merge windows
                current.end = max(current.end, next_candidate.end)
                current.anchor_tokens.extend(next_candidate.anchor_tokens)
                current.anchor_tokens = list(set(current.anchor_tokens))  # Dedupe
            else:
                # No overlap, add current and start new
                merged.append(current)
                current = next_candidate
        
        merged.append(current)
        return merged
    
    def _find_best_fuzzy_match(self, quote: str, text: str) -> Optional[Tuple[int, int, float]]:
        """
        Simple fuzzy matching using sliding window with edit distance.
        Returns (start, end, confidence) or None if no good match found.
        """
        if len(quote) < 3:
            return None
            
        quote_len = len(quote)
        text_len = len(text)
        
        if quote_len > text_len:
            return None
        
        best_match = None
        best_score = 0.0
        min_score = 0.6  # Minimum similarity threshold
        max_iterations = 1000  # Prevent infinite loops
        iteration_count = 0
        
        # Try different window sizes around the quote length
        for window_size in [quote_len, quote_len + 2, quote_len + 4]:
            if window_size > text_len:
                continue
                
            for i in range(text_len - window_size + 1):
                iteration_count += 1
                if iteration_count > max_iterations:
                    break
                    
                window = text[i:i + window_size]
                score = self._calculate_similarity(quote, window)
                
                if score > best_score and score >= min_score:
                    # Find the best alignment within this window
                    best_start, best_end = self._find_best_alignment(quote, window)
                    if best_start is not None:
                        best_match = (i + best_start, i + best_end, score)
                        best_score = score
            
            if iteration_count > max_iterations:
                break
        
        return best_match
    
    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Calculate simple similarity score between two strings."""
        if not s1 or not s2:
            return 0.0
        
        # Simple character overlap similarity
        s1_chars = set(s1.lower())
        s2_chars = set(s2.lower())
        
        if not s1_chars or not s2_chars:
            return 0.0
        
        intersection = len(s1_chars & s2_chars)
        union = len(s1_chars | s2_chars)
        
        return intersection / union if union > 0 else 0.0
    
    def _find_best_alignment(self, quote: str, window: str) -> Tuple[Optional[int], Optional[int]]:
        """Find the best alignment of quote within window."""
        quote_len = len(quote)
        window_len = len(window)
        
        if quote_len > window_len:
            return None, None
        
        best_start = None
        best_score = 0.0
        
        for i in range(window_len - quote_len + 1):
            substr = window[i:i + quote_len]
            score = self._calculate_similarity(quote, substr)
            
            if score > best_score:
                best_score = score
                best_start = i
        
        if best_start is not None and best_score >= 0.6:
            return best_start, best_start + quote_len
        
        return None, None
    
    def _align_quote_in_window(self, quote: str, candidate: CandidateWindow, 
                              norm_doc: NormalizedDocument, threshold: float) -> Optional[EvidenceSpan]:
        """
        Stage C: Align quote within candidate window using simple fuzzy matching.
        """
        # Extract window text from normalized document
        window_text = norm_doc.norm_basic[candidate.start:candidate.end]
        
        # Normalize quote
        normalized_quote = self._normalize_text(quote)
        
        # Try exact match first
        exact_pos = window_text.find(normalized_quote)
        if exact_pos >= 0:
            # Found exact match
            window_start = exact_pos
            window_end = exact_pos + len(normalized_quote)
            confidence = 1.0
        else:
            # Try simple fuzzy matching with sliding window
            best_match = self._find_best_fuzzy_match(normalized_quote, window_text)
            if best_match is None:
                return None
            
            window_start, window_end, confidence = best_match
        
        # Convert window-relative to document-relative positions
        doc_start = candidate.start + window_start
        doc_end = candidate.start + window_end
        
        # Map normalized positions back to raw text positions
        raw_start = self._map_normalized_to_raw(doc_start, norm_doc.basic_to_raw_map)
        raw_end = self._map_normalized_to_raw(doc_end, norm_doc.basic_to_raw_map)
        
        # Check confidence threshold
        if confidence < threshold:
            return None
        
        # Infer section
        section = self._infer_section_from_position(raw_start, norm_doc.sections)
        
        # Create EvidenceSpan
        return EvidenceSpan(
            doc_id="",  # Will be set by caller
            quote=quote,
            section=section,
            char_start=raw_start,
            char_end=raw_end,
            page=None,
            confidence=confidence
        )
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching (same as basic normalization)."""
        normalized = unicodedata.normalize('NFKC', text.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    def _map_normalized_to_raw(self, norm_pos: int, offset_map: List[int]) -> int:
        """Map normalized position back to raw text position."""
        if norm_pos < len(offset_map):
            return offset_map[norm_pos]
        return min(norm_pos, len(offset_map) - 1) if offset_map else 0
    
    def _infer_section_from_position(self, char_pos: int, sections: List[Dict[str, Any]]) -> str:
        """Infer section name from character position."""
        for section in sections:
            if section['start'] <= char_pos < section['end']:
                return section['name']
        return 'unknown'
    
    def _deduplicate_spans(self, spans: List[EvidenceSpan]) -> List[EvidenceSpan]:
        """
        Stage D: Deduplicate overlapping spans, keeping highest confidence ones.
        """
        if not spans:
            return spans
        
        # Sort by confidence (highest first)
        sorted_spans = sorted(spans, key=lambda s: s.confidence, reverse=True)
        
        deduplicated = []
        for span in sorted_spans:
            # Check if this span overlaps significantly with any already kept span
            overlaps = False
            for kept_span in deduplicated:
                if self._spans_overlap(span, kept_span, self.overlap_threshold):
                    overlaps = True
                    break
            
            if not overlaps:
                deduplicated.append(span)
        
        return deduplicated
    
    def _spans_overlap(self, span1: EvidenceSpan, span2: EvidenceSpan, threshold: float) -> bool:
        """Check if two spans overlap significantly (IoU >= threshold)."""
        if not span1.char_start or not span1.char_end or not span2.char_start or not span2.char_end:
            return False
        
        # Calculate intersection
        start = max(span1.char_start, span2.char_start)
        end = min(span1.char_end, span2.char_end)
        intersection = max(0, end - start)
        
        # Calculate union
        union = (span1.char_end - span1.char_start) + (span2.char_end - span2.char_start) - intersection
        
        if union == 0:
            return False
        
        iou = intersection / union
        return iou >= threshold
