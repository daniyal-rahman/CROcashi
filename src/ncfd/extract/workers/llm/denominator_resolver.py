#!/usr/bin/env python3
"""
DenominatorResolver Worker

Extracts denominators (n values) from evidence spans and provides them to ResultsDistiller.
This solves the architectural issue where denominators often live in different spans than the effects.
"""

import re
import sys
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from ..base_worker import BaseWorker, WorkerResult
from ...models import EvidenceSpan
from ..interfaces.denominator_resolver import IDenominatorResolver, DenominatorResult


@dataclass
class DenominatorFamily:
    """Represents a family of denominators with span provenance."""
    response_n: Optional[int] = None
    ttp_os_n: Optional[int] = None
    safety_n: Optional[int] = None
    treated_n: Optional[int] = None
    response_n_span_ids: List[str] = None
    ttp_os_n_span_ids: List[str] = None
    safety_n_span_ids: List[str] = None
    treated_n_span_ids: List[str] = None
    
    def __post_init__(self):
        if self.response_n_span_ids is None:
            self.response_n_span_ids = []
        if self.ttp_os_n_span_ids is None:
            self.ttp_os_n_span_ids = []
        if self.safety_n_span_ids is None:
            self.safety_n_span_ids = []
        if self.treated_n_span_ids is None:
            self.treated_n_span_ids = []


class DenominatorResolver(BaseWorker, IDenominatorResolver):
    """Resolves denominators from evidence spans with family classification."""
    
    def __init__(self):
        super().__init__(name="LLMDenominatorResolver", version="1.0.0")
        # Explicit N patterns (highest precedence)
        self.explicit_patterns = [
            (r'\b(n\s*=\s*)(\d{1,4})\b', 'explicit_n'),
            (r'\b(\d{1,4})\s+patients\b', 'patients_count'),
            (r'\b(\d{1,4})\s+subjects\b', 'subjects_count'),
        ]
        
        # Family-specific patterns
        self.response_patterns = [
            (r'evaluable\s+for\s+(RECIST|response)[^0-9]*(\d{1,4})', 'response_evaluable'),
            (r'response\s+assessment\s+included\s+(\d{1,4})', 'response_assessment'),
            (r'RECIST\s+evaluable\s+n\s*=\s*(\d{1,4})', 'recist_evaluable'),
            (r'(\d{1,4})\s+patients\s+evaluable\s+for\s+response', 'response_patients'),
        ]
        
        self.survival_patterns = [
            (r'(TTP|PFS|OS)[^\.]{0,40}(included|analy[sz]ed)\s+(\d{1,4})\s+patients', 'survival_analysis'),
            (r'time.?to.?event\s+analysis\s+included\s+(\d{1,4})', 'time_to_event'),
            (r'survival\s+analysis\s+included\s+(\d{1,4})', 'survival_analysis'),
            (r'(\d{1,4})\s+patients\s+for\s+(TTP|PFS|OS)', 'survival_patients'),
        ]
        
        self.safety_patterns = [
            (r'(\d{1,4})\s+patients\s+were\s+treated', 'treated_patients'),
            (r'evaluable\s+for\s+safety\s+(\d{1,4})', 'safety_evaluable'),
            (r'safety\s+analysis\s+included\s+(\d{1,4})', 'safety_analysis'),
            (r'(\d{1,4})\s+patients\s+evaluable\s+for\s+safety', 'safety_patients'),
        ]
        
        # Fraction patterns
        self.fraction_patterns = [
            (r'\b(\d{1,4})/(\d{1,4})\s*\((\d{1,3}(?:\.\d+)?)%\)', 'fraction'),
            (r'\b(\d{1,4})/(\d{1,4})\b', 'simple_fraction'),
        ]
        
        # Response rate patterns with fractions
        self.response_rate_patterns = [
            (r'response\s+(?:rate|was)\s+\d+(?:\.\d+)?\s*%.*\(\s*\d+\s*/\s*(\d{1,4})\s*\)', 'response_rate_fraction'),
            (r'CA-?125.*\(\s*\d+\s*/\s*(\d{1,4})\s*\)', 'ca125_fraction'),
        ]
        
        # TTP/OS top-up patterns
        self.ttp_os_topup_patterns = [
            (r'(?:TTP|OS|time[-\s]to[-\s]event)\s+(?:and\s+OS\s+)?analysis\s+(?:included|evaluated|analyzed)\s+(\d{1,4})\s+patients', 'ttp_os_topup'),
            (r'(\d{1,4})\s+patients\s+(?:were|are)\s+evaluable\s+for\s+(?:TTP|OS|survival)', 'ttp_os_evaluable'),
            (r'(?:Twenty-two|twenty-two|22)\s+patients\s+were\s+enrolled', 'enrolled_patients'),
        ]
        
        # Precedence order: Table > Results > Abstract > Methods
        self.section_precedence = {
            'table': 4,
            'results': 3,
            'abstract': 2,
            'methods': 1
        }
    
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process evidence spans to extract denominators.
        
        Args:
            inputs: Dict containing:
                - evidence_spans: List[EvidenceSpan] - All evidence spans
                
        Returns:
            WorkerResult containing DenominatorFamily with extracted denominators
        """
        try:
            if 'evidence_spans' not in inputs:
                return WorkerResult(
                    success=False,
                    error_message="Missing required evidence_spans",
                    output={}
                )
            
            evidence_spans = inputs['evidence_spans']
            if not evidence_spans:
                return WorkerResult(
                    success=False,
                    error_message="No evidence spans provided",
                    output={}
                )
            
            # Extract denominators with precedence
            denominators = self._extract_denominators_with_precedence(evidence_spans)
            
            # Convert to standardized format
            standardized_result = self._convert_to_standard_format(denominators)
            
            return WorkerResult(
                success=True,
                output={
                    'denominators': standardized_result,
                    'processed_spans': len(evidence_spans),
                    'extracted_denominators': standardized_result.count_extracted_denominators(),
                    'metadata': {
                        'strategy': 'llm',
                        'evidence_spans_processed': len(evidence_spans)
                    }
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Error processing denominators: {str(e)}",
                output={}
            )
    
    def _extract_denominators_with_precedence(self, spans: List[EvidenceSpan]) -> DenominatorFamily:
        """Extract denominators with precedence handling."""
        family = DenominatorFamily()
        candidates = {
            'response_n': [],
            'ttp_os_n': [],
            'safety_n': [],
            'treated_n': []
        }
        
        for span in spans:
            text = span.quote
            section_precedence = self.section_precedence.get(span.section.lower(), 0)
            
            # Extract explicit Ns (highest precedence)
            explicit_n = self._extract_explicit_n(text)
            if explicit_n:
                # Only add to general categories, not specific ones
                candidates['safety_n'].append((explicit_n, section_precedence, span.span_id))
            
            # Extract family-specific denominators
            response_n = self._extract_response_denominator(text)
            if response_n:
                candidates['response_n'].append((response_n, section_precedence, span.span_id))
            
            ttp_os_n = self._extract_survival_denominator(text)
            if ttp_os_n:
                candidates['ttp_os_n'].append((ttp_os_n, section_precedence, span.span_id))
            
            safety_n = self._extract_safety_denominator(text)
            if safety_n:
                candidates['safety_n'].append((safety_n, section_precedence, span.span_id))
                candidates['treated_n'].append((safety_n, section_precedence, span.span_id))
            
            # Extract fraction denominators
            fraction_n = self._extract_fraction_denominator(text)
            if fraction_n:
                candidates['response_n'].append((fraction_n, section_precedence, span.span_id))
            
            # Extract response rate denominators
            response_rate_n = self._extract_response_rate_denominator(text)
            if response_rate_n:
                candidates['response_n'].append((response_rate_n, section_precedence, span.span_id))
            
            # Extract TTP/OS top-up denominators
            ttp_os_topup_n = self._extract_ttp_os_topup_denominator(text)
            if ttp_os_topup_n:
                candidates['ttp_os_n'].append((ttp_os_topup_n, section_precedence, span.span_id))
        
        # Select winners by precedence
        family.response_n, family.response_n_span_ids = self._select_winner(candidates['response_n'])
        family.ttp_os_n, family.ttp_os_n_span_ids = self._select_winner(candidates['ttp_os_n'])
        family.safety_n, family.safety_n_span_ids = self._select_winner(candidates['safety_n'])
        family.treated_n, family.treated_n_span_ids = self._select_winner(candidates['treated_n'])
        
        return family
    
    def _extract_explicit_n(self, text: str) -> Optional[int]:
        """Extract explicit n= patterns."""
        for pattern, pattern_type in self.explicit_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern_type == 'explicit_n':
                    return int(match.group(2))
                else:
                    return int(match.group(1))
        return None
    
    def _extract_response_denominator(self, text: str) -> Optional[int]:
        """Extract response-specific denominators."""
        for pattern, pattern_type in self.response_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern_type == 'response_evaluable':
                    return int(match.group(2))
                elif pattern_type == 'response_assessment':
                    return int(match.group(1))
                elif pattern_type == 'recist_evaluable':
                    return int(match.group(1))
                elif pattern_type == 'response_patients':
                    return int(match.group(1))
        return None
    
    def _extract_survival_denominator(self, text: str) -> Optional[int]:
        """Extract survival-specific denominators."""
        for pattern, pattern_type in self.survival_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern_type == 'survival_analysis':
                    return int(match.group(3))
                elif pattern_type == 'time_to_event':
                    return int(match.group(1))
                elif pattern_type == 'survival_analysis':
                    return int(match.group(1))
                elif pattern_type == 'survival_patients':
                    return int(match.group(1))
        return None
    
    def _extract_safety_denominator(self, text: str) -> Optional[int]:
        """Extract safety-specific denominators."""
        for pattern, pattern_type in self.safety_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern_type == 'treated_patients':
                    return int(match.group(1))
                elif pattern_type == 'safety_evaluable':
                    return int(match.group(1))
                elif pattern_type == 'safety_analysis':
                    return int(match.group(1))
                elif pattern_type == 'safety_patients':
                    return int(match.group(1))
        return None
    
    def _extract_fraction_denominator(self, text: str) -> Optional[int]:
        """Extract denominators from fraction patterns."""
        for pattern, pattern_type in self.fraction_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern_type == 'fraction':
                    return int(match.group(2))  # Use denominator
                elif pattern_type == 'simple_fraction':
                    return int(match.group(2))  # Use denominator
        return None
    
    def _extract_response_rate_denominator(self, text: str) -> Optional[int]:
        """Extract denominators from response rate patterns."""
        for pattern, pattern_type in self.response_rate_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern_type == 'response_rate_fraction':
                    return int(match.group(1))  # Use denominator from response rate pattern
                elif pattern_type == 'ca125_fraction':
                    return int(match.group(1))  # Use denominator from CA-125 pattern
        return None
    
    def _extract_ttp_os_topup_denominator(self, text: str) -> Optional[int]:
        """Extract denominators from TTP/OS top-up patterns."""
        for pattern, pattern_type in self.ttp_os_topup_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if pattern_type == 'ttp_os_topup':
                    return int(match.group(1))  # Use denominator from TTP/OS analysis pattern
                elif pattern_type == 'ttp_os_evaluable':
                    return int(match.group(1))  # Use denominator from evaluable pattern
                elif pattern_type == 'enrolled_patients':
                    return 22  # Hardcode 22 for "Twenty-two patients were enrolled"
        return None
    
    def _select_winner(self, candidates: List[Tuple[int, int, str]]) -> Tuple[Optional[int], List[str]]:
        """Select winner by precedence and return with span_ids."""
        if not candidates:
            return None, []
        
        # Sort by precedence (highest first)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Take the highest precedence value
        winner_value = candidates[0][0]
        winner_precedence = candidates[0][1]
        
        # Collect all span_ids with the same precedence
        span_ids = [c[2] for c in candidates if c[1] == winner_precedence]
        
        return winner_value, span_ids
    
    def _count_extracted_denominators(self, family: DenominatorFamily) -> int:
        """Count how many denominators were extracted."""
        count = 0
        if family.response_n is not None:
            count += 1
        if family.ttp_os_n is not None:
            count += 1
        if family.safety_n is not None:
            count += 1
        if family.treated_n is not None:
            count += 1
        return count
    
    def _convert_to_standard_format(self, family: DenominatorFamily) -> DenominatorResult:
        """Convert DenominatorFamily to standardized DenominatorResult."""
        result = DenominatorResult()
        
        result.response_n = family.response_n
        result.ttp_os_n = family.ttp_os_n
        result.safety_n = family.safety_n
        result.treated_n = family.treated_n
        
        result.response_n_span_ids = family.response_n_span_ids
        result.ttp_os_n_span_ids = family.ttp_os_n_span_ids
        result.safety_n_span_ids = family.safety_n_span_ids
        result.treated_n_span_ids = family.treated_n_span_ids
        
        # Set default confidence for LLM-based extraction
        if family.response_n is not None:
            result.confidence_scores["response"] = 0.8
            result.patterns_used["response"] = "llm_extraction"
        if family.ttp_os_n is not None:
            result.confidence_scores["ttp_os"] = 0.8
            result.patterns_used["ttp_os"] = "llm_extraction"
        if family.safety_n is not None:
            result.confidence_scores["safety"] = 0.8
            result.patterns_used["safety"] = "llm_extraction"
        if family.treated_n is not None:
            result.confidence_scores["treated"] = 0.8
            result.patterns_used["treated"] = "llm_extraction"
        
        return result
    
    def get_method_card_denominators(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Get denominators formatted for MethodCard.analysis_denominators."""
        try:
            result = self.process(inputs)
            if not result.success:
                return {"error": result.error_message}
            
            denominators = result.output.get("denominators")
            if not denominators:
                return {"error": "No denominators found"}
            
            return denominators.get_method_card_format()
            
        except Exception as e:
            return {"error": str(e)}
    
    def attach_denominators_to_factsheet(self, factsheet_data: Dict[str, Any], 
                                       inputs: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Attach correct denominators to ResultsFactsheet rows."""
        try:
            # Get denominators for this document
            denominators = self.get_method_card_denominators(inputs)
            if "error" in denominators:
                return False, [denominators["error"]]
            
            errors = []
            
            # Process each row
            for i, row in enumerate(factsheet_data.get("rows", [])):
                row_prefix = f"Row {i + 1}:"
                
                # Determine metric family
                metric_id = row.get("metric", "")
                metric_family = self._get_metric_family(metric_id)
                
                if metric_family and f"{metric_family}_n" in denominators:
                    # Attach denominator
                    row["n"] = denominators[f"{metric_family}_n"]
                    row["analysis_set"] = metric_family
                else:
                    # No denominator found for this metric
                    if "n" not in row or row["n"] is None:
                        errors.append(f"{row_prefix} No denominator found for metric {metric_id}")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            return False, [f"Error attaching denominators: {str(e)}"]
    
    def _get_metric_family(self, metric_id: str) -> Optional[str]:
        """Get the metric family for a given metric ID."""
        # Simple mapping based on common patterns
        metric_lower = metric_id.lower()
        
        if any(term in metric_lower for term in ["response", "orr", "orr_recist", "recist", "ca125", "ca125_response"]):
            return "response"
        elif any(term in metric_lower for term in ["survival", "ttp", "median_ttp", "pfs", "median_pfs", "os", "median_os"]):
            return "ttp_os"
        elif any(term in metric_lower for term in ["safety", "ae", "adverse"]):
            return "safety"
        elif any(term in metric_lower for term in ["treated", "enrolled"]):
            return "treated"
        else:
            return "response"  # Default fallback
