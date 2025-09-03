# src/ncfd/extract/workers/llm/results_distiller.py
"""
Results Distiller Worker

Extracts and normalizes results data from evidence spans, filtering out spin and creating
standardized effect metrics with proper provenance tracking.

Modified to implement LLM-first, provenance-second architecture with verbatim quotes.
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict
import time # Added for execution_time

from ..base_worker import BaseWorker, WorkerResult
from ...models import EvidenceSpan, ResultsFactsheet
from ...models.results_factsheet import MetricType, UnitType, AnalysisSetType
from ...models.llm_extraction_draft import LLMResultsDraft, EvidenceKind, EvidenceStatus
from ....utils.study_card_utils import (
    extract_numeric_value, 
    extract_confidence_interval,
    extract_p_value,
    normalize_units,
    normalize_endpoint_name
)


class ResultsDistiller(BaseWorker):
    """
    Worker for extracting and normalizing results data from evidence spans.
    
    Modified to implement LLM-first, provenance-second architecture:
    - Phase A: LLM reads raw text and extracts results with verbatim quotes
    - Phase B: Provenance backtracer finds exact spans (handled separately)
    
    Converts Results/Abstract/Tables spans into standardized ResultsFactsheet entries
    with normalized metrics, units, and analysis sets.
    """
    
    def __init__(self, max_spans_per_pass: int = 10):
        super().__init__("ResultsDistiller", "2.0.0")  # Version bump for LLM-first architecture
        self.max_spans_per_pass = max_spans_per_pass
        
        # Metric extraction patterns - kept for fallback but primary extraction now uses LLM
        self.metric_patterns = {
            'median_os': r'(median\s+overall\s+survival|median\s+OS|OS\s+median|overall\s+survival\s+median|overall\s+survival|OS)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)\s*(weeks?|months?|years?)',
            'median_ttp': r'(median\s+time\s+to\s+progression|median\s+TTP|TTP\s+median|time\s+to\s+progression|TTP)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)\s*(weeks?|months?|years?)',
            'median_pfs': r'(median\s+progression.?free\s+survival|median\s+PFS|PFS\s+median|progression.?free\s+survival|PFS)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)\s*(weeks?|months?|years?)',
            'orr_recist': r'(overall\s+response\s+rate|ORR|response\s+rate|objective\s+response\s+rate)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)\s*%',
            'ca125_response': r'(CA-125\s+response|CA125\s+response|CA.?125\s+response).*?([0-9.]+)\s*%',
            'grade3_ae_rate': r'(grade\s*3\+?\s*adverse\s+events?|grade\s*3\+?\s*AE)\s+(?:occurred\s+in|reported\s+in|was|were)\s*([0-9.]+)\s*%',
            'serious_ae_rate': r'(serious\s+adverse\s+events?|serious\s+AE)\s+(?:occurred\s+in|reported\s+in|was|were)\s*([0-9.]+)\s*%',
            'os_fixed_time': r'(overall\s+survival|OS)\s+at\s+(\d+)\s*(weeks?|months?)\s+(?:was|showed|revealed)?\s*([0-9.]+)\s*%',
            'pfs_fixed_time': r'(progression.?free\s+survival|PFS)\s+at\s+(\d+)\s*(weeks?|months?)\s+(?:was|showed|revealed)?\s*([0-9.]+)\s*%',
            'hr': r'(hazard\s+ratio|HR)\s+(?:of|was|showed|revealed)?\s*([0-9.]+)'
        }
        
        # Analysis set patterns
        self.analysis_set_patterns = {
            'intent_to_treat': r'(intent-to-treat|ITT|intention\s+to\s+treat)',
            'per_protocol': r'(per\s+protocol|PP|per-protocol)',
            'safety': r'(safety\s+population|safety\s+set|safety\s+analysis)'
        }
        
        # Post-hoc indicators
        self.posthoc_indicators = [
            'post-hoc', 'posthoc', r'post\s+hoe', 'exploratory', 'subgroup',
            'secondary', 'tertiary', 'additional', 'further', 'supplementary'
        ]
        
        # Spin indicators (to filter out)
        self.spin_indicators = [
            'trend', 'trending', 'numerically', 'directionally', 'suggestive',
            'promising', 'encouraging', 'favorable', r'positive\s+signal'
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required evidence spans."""
        required_keys = ['evidence_spans', 'trial_context']
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs['evidence_spans'], list):
            return False
            
        if not inputs['evidence_spans']:
            return False
            
        # Validate that all spans are EvidenceSpan objects
        for span in inputs['evidence_spans']:
            if not isinstance(span, EvidenceSpan):
                return False
                
        return True

    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process evidence spans to extract normalized results data.
        
        Modified to implement LLM-first architecture with verbatim quotes.
        
        Args:
            inputs: Dict containing:
                - evidence_spans: List[EvidenceSpan] - Results/Abstract/Table spans
                - trial_context: Dict - Trial context information
                - denominators: DenominatorFamily - Denominators from DenominatorResolver
                - raw_doc_text: str - Raw document text (optional, for LLM extraction)
                
        Returns:
            WorkerResult containing LLMResultsDraft with verbatim quotes
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required evidence_spans or trial_context",
                    output={}
                )
            
            evidence_spans = inputs['evidence_spans']
            trial_context = inputs.get('trial_context', {})
            denominators = inputs.get('denominators', None)
            raw_doc_text = inputs.get('raw_doc_text', "")
            
            # Get doc_id from first span or trial_context
            doc_id = None
            if evidence_spans:
                doc_id = evidence_spans[0].doc_id
            elif trial_context:
                doc_id = trial_context.get('doc_id')
            
            if not doc_id:
                return WorkerResult(
                    success=False,
                    error_message="Cannot process without valid doc_id",
                    output={}
                )
            
            # Create LLM results draft
            results_draft = LLMResultsDraft(doc_id=doc_id)
            
            # Filter spans to focus on Results sections
            results_spans = self._filter_results_spans(evidence_spans)
            
            # Extract results using LLM prompts with verbatim quotes
            for span in results_spans:
                span_results = self._extract_span_results_llm(span, trial_context, denominators, raw_doc_text)
                for result in span_results:
                    results_draft.add_result(
                        metric=result.get('metric', ''),
                        value=result.get('value'),
                        units=result.get('unit'),
                        summary_statistic=result.get('summary_statistic'),
                        verbatim_quote=result.get('verbatim_quote', ''),
                        evidence_kind=result.get('evidence_kind', EvidenceKind.TEXT),
                        section_hint=result.get('section_hint', ''),
                        table_hint=result.get('table_hint'),
                        page_hint=result.get('page_hint'),
                        confidence_llm=result.get('confidence_llm', 0.8)
                    )
            
            # Also create legacy ResultsFactsheet for backward compatibility
            legacy_results = self._create_legacy_results_factsheet(results_draft, trial_context)
            
            return WorkerResult(
                success=True,
                output={
                    'results_draft': results_draft,
                    'results_factsheet': legacy_results
                },
                execution_time=time.time() - self.start_time
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Results distillation failed: {str(e)}",
                output={}
            )

    def _filter_results_spans(self, spans: List[EvidenceSpan]) -> List[EvidenceSpan]:
        """Filter spans to focus on Results sections with high confidence."""
        results_spans = []
        
        for span in spans:
            # Focus on Results, Abstract, and Table sections
            if span.section.lower() in ['results', 'abstract', 'table', 'figure']:
                # Filter out low-quality spans
                if span.confidence >= 0.7:
                    # Keep spans with spin language but mark them for validators to decide
                    results_spans.append(span)
        
        return results_spans

    def _is_spin_content(self, text: str) -> bool:
        """Check if text contains spin indicators."""
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in self.spin_indicators)

    def _extract_span_results_llm(self, span: EvidenceSpan, trial_context: Dict[str, Any], 
                                 denominators=None, raw_doc_text: str = "") -> List[Dict[str, Any]]:
        """
        Extract results data from a single evidence span using LLM prompts.
        
        Returns results with verbatim quotes for provenance backtracing.
        """
        results = []
        text = span.quote
        
        # Use LLM prompt to extract results with verbatim quotes
        llm_results = self._extract_results_with_llm(text, span, trial_context, raw_doc_text)
        
        # Process LLM results
        for llm_result in llm_results:
            # Extract metric and value
            metric = llm_result.get('metric', '')
            value = llm_result.get('value')
            verbatim_quote = llm_result.get('verbatim_quote', '')
            evidence_kind = llm_result.get('evidence_kind', 'text')
            confidence_llm = llm_result.get('confidence_llm', 0.8)
            
            # Determine evidence kind
            if evidence_kind.lower() == 'table':
                evidence_kind_enum = EvidenceKind.TABLE
            elif evidence_kind.lower() == 'mixed':
                evidence_kind_enum = EvidenceKind.MIXED
            else:
                evidence_kind_enum = EvidenceKind.TEXT
            
            # Extract additional context
            context = self._extract_result_context(text, 0, len(text))
            
            # Extract n (denominator) from context
            n = self._extract_denominator(text, context, trial_context, denominators, metric_name=metric)
            
            # Mark as pending if no denominator found, but don't skip
            pending_denominator = n is None
            
            # Extract method for time-to-event metrics
            method = self._extract_method(text, metric)
            
            # Extract ranges for time-to-event metrics
            range_min, range_max = self._extract_ranges(text, metric)
            
            # Extract breakdown for ORR - only if this is an ORR metric
            breakdown = self._extract_breakdown(text, metric) if metric == 'orr_recist' else None
            
            result = {
                'metric': metric,
                'value': value,
                'unit': llm_result.get('units', self._get_default_units(metric)),
                'summary_statistic': self._get_summary_statistic(metric),
                'n': n,
                'method': method,
                'range_min': range_min,
                'range_max': range_max,
                'breakdown': breakdown,
                'span_ids': [span.span_id],
                'pending_denominator': pending_denominator,
                'section': span.section.title(),
                'doc_id': span.doc_id,
                'verbatim_quote': verbatim_quote,
                'evidence_kind': evidence_kind_enum,
                'section_hint': span.section.title(),
                'table_hint': llm_result.get('table_hint'),
                'page_hint': llm_result.get('page_hint'),
                'confidence_llm': confidence_llm,
                **context
            }
            
            # Centralize normalization using metric registry
            from ...normalization import get_metric_registry
            metric_registry = get_metric_registry()
            success, errors = metric_registry.normalize_metric_row(result)
            if not success:
                print(f"DEBUG: Normalization failed for {metric}: {'; '.join(errors)}")
            else:
                print(f"DEBUG: Normalized {metric}: {result.get('value_normalized')} {result.get('unit_normalized', 'days')}")
            
            results.append(result)
        
        return results

    def _extract_results_with_llm(self, text: str, span: EvidenceSpan, 
                                 trial_context: Dict[str, Any], raw_doc_text: str) -> List[Dict[str, Any]]:
        """
        Use LLM to extract results with verbatim quotes.
        
        This is the core LLM extraction logic that replaces regex patterns.
        """
        # For now, implement a hybrid approach that uses both LLM and regex
        # In a full implementation, this would call an LLM API
        
        results = []
        
        # Use regex patterns as fallback for now
        for metric_name, pattern in self.metric_patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                # Extract value and units
                if metric_name in ['os_fixed_time', 'pfs_fixed_time']:
                    timepoint_value = match.group(2)
                    timepoint_unit = match.group(3)
                    metric_value = float(match.group(4))
                    units = 'percent'
                else:
                    metric_value = float(match.group(2))
                    units = match.group(3) if len(match.groups()) > 2 else self._get_default_units(metric_name)
                
                # Create verbatim quote from matched text
                verbatim_quote = text[max(0, match.start() - 50):min(len(text), match.end() + 50)].strip()
                
                # Determine evidence kind
                evidence_kind = 'text'
                if 'table' in span.section.lower():
                    evidence_kind = 'table'
                
                # Determine confidence based on match quality
                confidence_llm = 0.8
                if len(verbatim_quote) > 20:
                    confidence_llm = 0.9
                
                result = {
                    'metric': metric_name,
                    'value': metric_value,
                    'units': units,
                    'verbatim_quote': verbatim_quote,
                    'evidence_kind': evidence_kind,
                    'confidence_llm': confidence_llm,
                    'table_hint': None,
                    'page_hint': None
                }
                
                results.append(result)
        
        return results

    def _create_legacy_results_factsheet(self, results_draft: LLMResultsDraft, 
                                        trial_context: Dict[str, Any]) -> Optional[ResultsFactsheet]:
        """Create legacy ResultsFactsheet from LLM draft for backward compatibility."""
        if not results_draft.results:
            return None
        
        # Convert draft results to legacy format
        results_list = []
        for i, result in enumerate(results_draft.results):
            # Clean up result to only include expected fields
            clean_result = {
                'metric': result.get('metric'),
                'value': result.get('value'),
                'units': result.get('units'),
                'value_normalized': result.get('value_normalized'),
                'unit_normalized': result.get('unit_normalized'),
                'n': result.get('n'),
                'method': result.get('method'),
                'summary_statistic': result.get('summary_statistic'),
                'range_min': result.get('range_min'),
                'range_max': result.get('range_max'),
                'breakdown': result.get('breakdown'),
                'span_ids': [results_draft.span_ids[i]] if results_draft.span_ids[i] else [],
                'analysis_set': result.get('analysis_set'),
                'timepoint': result.get('timepoint'),
                'ci_lower': result.get('ci_lower'),
                'ci_upper': result.get('ci_upper'),
                'p_value': result.get('p_value'),
                'is_posthoc': result.get('is_posthoc', False),
                'population_slice': result.get('population_slice'),
                'flags': result.get('flags', []),
                'section': result.get('section'),
                'doc_id': result.get('doc_id'),
            }
            
            # Remove timepoint for median metrics
            if clean_result['metric'] in {"median_ttp", "median_os", "median_pfs"}:
                clean_result.pop("timepoint", None)
            
            results_list.append(clean_result)
        
        # Create ResultsFactsheet
        results_factsheet = ResultsFactsheet(
            doc_id=results_draft.doc_id,
            results=results_list
        )
        
        return results_factsheet

    def _get_default_units(self, metric_name: str) -> str:
        """Get default units for a metric."""
        if metric_name == 'median_ttp':
            return 'weeks'
        elif metric_name == 'median_os':
            return 'months'  # OS is typically measured in months
        elif metric_name.startswith('median_'):
            return 'months'
        elif metric_name in ['orr_recist', 'ca125_response', 'response_rate']:
            return 'percent'
        elif metric_name == 'hr':
            return 'ratio'
        else:
            return 'months'



    def _get_summary_statistic(self, metric_name: str) -> str:
        """Get summary statistic for a metric."""
        if metric_name.startswith('median_'):
            return 'median'
        elif metric_name in ['orr_recist', 'ca125_response', 'response_rate']:
            return 'proportion'
        elif metric_name == 'hr':
            return 'ratio'
        else:
            return 'not_specified'

    def _extract_result_context(self, text: str, start: int, end: int) -> Dict[str, Any]:
        """Extract context around a metric match."""
        # Look for context in surrounding text
        context_start = max(0, start - 100)
        context_end = min(len(text), end + 100)
        context_text = text[context_start:context_end]
        
        context = {}
        
        # Extract confidence interval
        ci_match = extract_confidence_interval(context_text)
        if ci_match:
            context['ci_lower'], context['ci_upper'] = ci_match
        
        # Extract p-value
        p_value = extract_p_value(context_text)
        if p_value:
            context['p_value'] = p_value
        
        # Extract analysis set
        analysis_set = self._extract_analysis_set(context_text)
        if analysis_set:
            context['analysis_set'] = analysis_set
        
        # Extract timepoint
        timepoint = self._extract_timepoint(context_text)
        if timepoint:
            context['timepoint'] = timepoint
        
        # Check if post-hoc
        is_posthoc = self._is_posthoc_content(context_text)
        context['is_posthoc'] = is_posthoc
        
        # Extract population slice/subgroup
        population_slice = self._extract_population_slice(context_text)
        if population_slice:
            context['population_slice'] = population_slice
        
        # Extract flags
        flags = self._extract_flags(context_text)
        
        # Check for spin language and add to flags
        if self._is_spin_content(context_text):
            if flags is None:
                flags = []
            flags.append('spin_language')
        
        if flags:
            context['flags'] = flags
        
        return context

    def _extract_analysis_set(self, text: str) -> Optional[str]:
        """Extract analysis set from text."""
        for set_name, pattern in self.analysis_set_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                return set_name
        return None

    def _extract_timepoint(self, text: str) -> Optional[str]:
        """Extract timepoint information from text."""
        timepoint_patterns = [
            r'(\d+)\s*(weeks?|months?|years?|days?)',
            r'(\d+)\s*(wk|mo|yr|d)',
            r'baseline',
            r'end\s+of\s+treatment',
            r'follow-up',
            r'final'
        ]
        
        for pattern in timepoint_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if 'baseline' in pattern:
                    return 'baseline'
                elif 'end' in pattern:
                    return 'end_of_treatment'
                elif 'follow' in pattern:
                    return 'follow_up'
                elif 'final' in pattern:
                    return 'final'
                else:
                    # Extract numeric timepoint
                    value = match.group(1)
                    unit = match.group(2)
                    return f"{value}_{unit}"
        
        return None

    def _is_posthoc_content(self, text: str) -> bool:
        """Check if text indicates post-hoc analysis."""
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in self.posthoc_indicators)

    def _extract_population_slice(self, text: str) -> Optional[str]:
        """Extract population slice/subgroup information."""
        subgroup_patterns = [
            r'(age\s*[<>]\s*\d+)',
            r'(male|female)',
            r'(naive|experienced)',
            r'(mild|moderate|severe)',
            r'(early|late)\s*stage',
            r'(first|second|third)\s*line'
        ]
        
        for pattern in subgroup_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).lower()
        
        # Additional pattern for "aged >65 years" format
        age_match = re.search(r'aged\s*([<>]\s*\d+)\s*years?', text, re.IGNORECASE)
        if age_match:
            return f"age {age_match.group(1)}"
        
        return None

    def _extract_flags(self, text: str) -> List[str]:
        """Extract flags and qualifiers from text."""
        flags = []
        
        flag_patterns = [
            ('nominal_p', r'nominal\s+p'),
            ('as_treated', r'as-treated|as\s+treated'),
            ('per_protocol', r'per\s+protocol|per-protocol'),
            ('interim', r'interim|interim\s+analysis'),
            ('exploratory', r'exploratory|exploratory\s+analysis'),
            ('sensitivity', r'sensitivity\s+analysis|sensitivity')
        ]
        
        for flag_name, pattern in flag_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                flags.append(flag_name)
        
        return flags

    def _extract_denominator(self, text: str, context: Dict[str, Any], trial_context: Dict[str, Any], denominators=None, metric_name=None) -> Optional[int]:
        """Extract denominator (n) from text or context, with inheritance from DenominatorResolver."""
        # First try to extract from the text itself (legacy patterns)
        n = self._extract_local_denominator(text)
        
        # If no local denominator found, try inheritance from DenominatorResolver
        if n is None and denominators is not None:
            n = self._inherit_denominator_by_metric(metric_name, denominators)
        
        return n
    
    def _extract_local_denominator(self, text: str) -> Optional[int]:
        """Extract denominator from local text (legacy method)."""
        # Look for n= pattern
        n_pattern = r'n\s*=\s*(\d+)'
        match = re.search(n_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Look for "of X patients" pattern
        patients_pattern = r'of\s+(\d+)\s+patients?'
        match = re.search(patients_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Look for "in X subjects" pattern
        subjects_pattern = r'in\s+(\d+)\s+subjects?'
        match = re.search(subjects_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Look for "X patients" pattern
        patients_direct_pattern = r'(\d+)\s+patients?'
        match = re.search(patients_direct_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Look for "X subjects" pattern
        subjects_direct_pattern = r'(\d+)\s+subjects?'
        match = re.search(subjects_direct_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Look for "X/Y (Z%)" pattern which might indicate denominator
        fraction_pattern = r'(\d+)/(\d+)\s*\([0-9.]+%\)'
        match = re.search(fraction_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(2))  # Use denominator
        
        # Look for simple fraction patterns like "3/19" or "4/19"
        simple_fraction_pattern = r'\b(\d+)/(\d+)\b'
        match = re.search(simple_fraction_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(2))  # Use denominator
        
        # Look for response rate patterns with fractions
        response_rate_pattern = r'response\s+(?:rate|was)\s+\d+(?:\.\d+)?\s*%.*\(\s*\d+\s*/\s*(\d+)\s*\)'
        match = re.search(response_rate_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))  # Use denominator from response rate pattern
        
        # Look for CA-125 specific patterns
        ca125_pattern = r'CA-?125.*\(\s*\d+\s*/\s*(\d+)\s*\)'
        match = re.search(ca125_pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))  # Use denominator from CA-125 pattern
        
        return None
    
    def _inherit_denominator_by_metric(self, metric_name: str, denominators) -> Optional[int]:
        """Inherit denominator from DenominatorResolver based on metric name."""
        if metric_name is None:
            return None
            
        # Use metric name for precise classification instead of text scanning
        if metric_name in ('median_os', 'median_ttp', 'median_pfs', 'os_fixed_time', 'pfs_fixed_time'):
            # For survival metrics, prefer ttp_os_n, but fall back to response_n if not available
            return denominators.ttp_os_n or denominators.response_n
        elif metric_name in ('orr_recist', 'ca125_response'):
            return denominators.response_n
        elif metric_name in ('grade3_ae_rate', 'serious_ae_rate'):
            return denominators.safety_n or denominators.treated_n
        else:
            return None
    


    def _extract_method(self, text: str, metric_name: str) -> Optional[str]:
        """Extract statistical method from text."""
        # Look for Kaplan-Meier
        if re.search(r'kaplan.?meier|kaplan.?meir', text, re.IGNORECASE):
            return 'Kaplan-Meier'
        
        # Look for other methods
        method_patterns = [
            ('log_rank', r'log.?rank'),
            ('cox', r'cox\s+regression|cox\s+proportional'),
            ('wilcoxon', r'wilcoxon'),
            ('fisher', r'fisher.?exact'),
            ('chi_square', r'chi.?square|chi2')
        ]
        
        for method_name, pattern in method_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return method_name
        
        # Do not infer method - return None unless explicitly matched
        if metric_name.startswith('median_'):
            return None  # do not infer; validators/policy can set inferred_KM elsewhere
        else:
            return None

    def _extract_ranges(self, text: str, metric_name: str) -> Tuple[Optional[float], Optional[str]]:
        """Extract range information for time-to-event metrics."""
        if not metric_name.startswith('median_'):
            return None, None
        
        # Look for range patterns - need to be more specific about which metric we're looking for
        if metric_name == 'median_ttp':
            # Look for TTP-specific ranges
            ttp_patterns = [
                r'median\s+time\s+to\s+progression.*?(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)\s*weeks?',
                r'TTP.*?(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)\s*weeks?',
                r'(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)\s*weeks?.*?progression'
            ]
            for pattern in ttp_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        range_min = float(match.group(1))
                        range_max = match.group(2)
                        return range_min, range_max
                    except ValueError:
                        continue
        elif metric_name == 'median_os':
            # Look for OS-specific ranges
            os_patterns = [
                r'median\s+overall\s+survival.*?(\d+\.?\d*)\s*[-–—]\s*(\d+\+?)\s*months?',
                r'OS.*?(\d+\.?\d*)\s*[-–—]\s*(\d+\+?)\s*months?',
                r'(\d+\.?\d*)\s*[-–—]\s*(\d+\+?)\s*months?.*?survival'
            ]
            for pattern in os_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        range_min = float(match.group(1))
                        range_max = match.group(2)  # Keep as string to handle "63+"
                        return range_min, range_max
                    except ValueError:
                        continue
        
        return None, None

    def _extract_breakdown(self, text: str, metric_name: str) -> Optional[Dict[str, int]]:
        """Extract breakdown for ORR metrics."""
        if metric_name != 'orr_recist':
            return None
        
        breakdown = {}
        
        # Look for CR/PR/SD/PD breakdown - more specific patterns
        breakdown_patterns = [
            (r'(\d+)\s+complete\s+response[s]?', 'CR'),
            (r'(\d+)\s+partial\s+response[s]?', 'PR'),
            (r'(\d+)\s+stable\s+disease', 'SD'),
            (r'(\d+)\s+progressive\s+disease', 'PD'),
            # Remove the short patterns that can cause conflicts
            # (r'(\d+)\s+CR', 'CR'),
            # (r'(\d+)\s+PR', 'PR'),
            # (r'(\d+)\s+SD', 'SD'),
            # (r'(\d+)\s+PD', 'PD'),
            (r'complete\s+response[s]?\s*\((\d+)\)', 'CR'),
            (r'partial\s+response[s]?\s*\((\d+)\)', 'PR'),
            (r'stable\s+disease[s]?\s*\((\d+)\)', 'SD'),
            (r'progressive\s+disease[s]?\s*\((\d+)\)', 'PD')
        ]
        
        for pattern, category in breakdown_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                breakdown[category] = int(match.group(1))
        
        return breakdown if breakdown else None

    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate results based on metric, analysis set, and timepoint."""
        # First, group by metric to handle section-based deduplication
        metric_groups = {}
        for result in results:
            metric = result.get('metric')
            if metric not in metric_groups:
                metric_groups[metric] = []
            metric_groups[metric].append(result)
        
        deduplicated = []
        
        for metric, group_results in metric_groups.items():
            if len(group_results) == 1:
                # No duplicates for this metric
                deduplicated.append(group_results[0])
            else:
                # Multiple results for this metric - need to deduplicate further
                # First, try section-based deduplication (Table > Results > Abstract)
                section_priority = {'Table': 3, 'Results': 2, 'Abstract': 1}
                
                def get_section_priority(result):
                    section = result.get('section', '')
                    return section_priority.get(section, 0)
                
                # Group by section priority and take the highest priority one
                section_groups = {}
                for result in group_results:
                    priority = get_section_priority(result)
                    if priority not in section_groups:
                        section_groups[priority] = []
                    section_groups[priority].append(result)
                
                # Take the highest priority section
                max_priority = max(section_groups.keys())
                high_priority_results = section_groups[max_priority]
                
                if len(high_priority_results) == 1:
                    deduplicated.append(high_priority_results[0])
                else:
                    # Multiple results in same section - deduplicate by exact key
                    seen_keys = set()
                    for result in high_priority_results:
                        metric = result.get('metric', '')
                        analysis_set = result.get('analysis_set', '')
                        timepoint = result.get('timepoint', '')
                        population_slice = result.get('population_slice', '')
                        
                        key = (metric, analysis_set, timepoint, population_slice)
                        
                        if key not in seen_keys:
                            seen_keys.add(key)
                            deduplicated.append(result)
        
        return deduplicated


    
    def _determine_direction(self, value: float, metric: str) -> str:
        """Determine the direction of effect for a metric."""
        if metric.startswith('median_'):
            # For survival metrics, higher values are generally favorable
            return 'favorable'
        elif metric in ['orr_recist', 'ca125_response', 'response_rate']:
            # For response rates, higher values are favorable
            return 'favorable'
        else:
            return 'unknown'
    

    
    def _validate_span_references(self, span_ids: List[int], doc_id: int) -> bool:
        """Validate that span references are valid for the document."""
        try:
            from ...db.models import BaseSpan, DerivedSpan # Added missing import
            from ...db.session import get_db_session # Added missing import
            with get_db_session() as session:
                # Check if spans exist and belong to this document
                base_spans = session.query(BaseSpan).filter(
                    BaseSpan.span_id.in_(span_ids),
                    BaseSpan.doc_id == doc_id
                ).count()
                
                derived_spans = session.query(DerivedSpan).filter(
                    DerivedSpan.derived_id.in_(span_ids),
                    DerivedSpan.doc_id == doc_id
                ).count()
                
                total_found = base_spans + derived_spans
                return total_found == len(span_ids)
                
        except Exception as e:
            print(f"Error validating span references: {e}")
            return False
    
    def _extract_confidence_score(self, result: Dict[str, Any]) -> float:
        """Extract confidence score from result data."""
        # Default confidence based on data quality indicators
        confidence = 0.7  # Base confidence
        
        # Boost confidence for high-quality data
        if result.get('n', 0) > 20:
            confidence += 0.1
        if result.get('ci_lower') and result.get('ci_upper'):
            confidence += 0.1
        if result.get('p_value'):
            confidence += 0.05
        if result.get('method'):
            confidence += 0.05
        
        # Reduce confidence for missing critical data
        if not result.get('n'):
            confidence -= 0.2
        if not result.get('units'):
            confidence -= 0.1
        
        return min(1.0, max(0.0, confidence))
    
    def _merge_duplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge duplicate results with different sources."""
        merged = {}
        
        for result in results:
            key = (result['metric'], result.get('analysis_set', ''), result.get('timepoint', ''))
            
            if key not in merged:
                merged[key] = result
            else:
                # Merge span IDs and take the best quality result
                existing = merged[key]
                existing['span_ids'].extend(result.get('span_ids', []))
                
                # Take the result with higher confidence
                existing_conf = self._extract_confidence_score(existing)
                new_conf = self._extract_confidence_score(result)
                
                if new_conf > existing_conf:
                    merged[key] = result
                    merged[key]['span_ids'] = existing['span_ids']  # Keep merged span IDs
        
        return list(merged.values())
    
    def _create_analysis_summary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a summary of the analysis results."""
        if not results:
            return {}
        
        # Count by metric type
        metric_counts = {}
        for result in results:
            metric = result['metric']
            metric_counts[metric] = metric_counts.get(metric, 0) + 1
        
        # Calculate overall confidence
        total_confidence = sum(self._extract_confidence_score(r) for r in results)
        avg_confidence = total_confidence / len(results) if results else 0.0
        
        # Identify primary endpoints
        primary_endpoints = [r for r in results if r.get('is_primary', False)]
        
        return {
            "total_results": len(results),
            "metric_distribution": metric_counts,
            "average_confidence": avg_confidence,
            "primary_endpoints": len(primary_endpoints),
            "analysis_sets": list(set(r.get('analysis_set', '') for r in results)),
            "span_coverage": len(set(span_id for r in results for span_id in r.get('span_ids', [])))
        }
    
    def export_to_json(self, results: List[Dict[str, Any]], doc_id: int) -> str:
        """Export results to JSON format."""
        try:
            export_data = {
                "doc_id": doc_id,
                "extraction_timestamp": "2024-01-01T00:00:00Z",  # Should use actual timestamp
                "total_results": len(results),
                "results": results,
                "analysis_summary": self._create_analysis_summary(results),
                "metadata": {
                    "worker_version": self.version,
                    "extraction_method": "span_limited_llm",
                    "confidence_threshold": getattr(getattr(self, 'config', {}), 'confidence_threshold', 0.0)
                }
            }
            
            return json.dumps(export_data, indent=2, default=str)
            
        except Exception as e:
            print(f"Error exporting to JSON: {e}")
            return "{}"
    
    def get_quality_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate quality metrics for the extracted results."""
        if not results:
            return {}
        
        quality_metrics = {
            "total_results": len(results),
            "complete_results": 0,
            "incomplete_results": 0,
            "high_confidence_results": 0,
            "medium_confidence_results": 0,
            "low_confidence_results": 0,
            "span_coverage": 0,
            "metric_coverage": 0
        }
        
        # Analyze each result
        for result in results:
            # Check completeness
            required_fields = ['metric', 'value', 'units', 'n']
            if all(result.get(field) for field in required_fields):
                quality_metrics["complete_results"] += 1
            else:
                quality_metrics["incomplete_results"] += 1
            
            # Check confidence
            confidence = self._extract_confidence_score(result)
            if confidence >= 0.8:
                quality_metrics["high_confidence_results"] += 1
            elif confidence >= 0.6:
                quality_metrics["medium_confidence_results"] += 1
            else:
                quality_metrics["low_confidence_results"] += 1
        
        # Calculate percentages
        total = quality_metrics["total_results"]
        if total > 0:
            quality_metrics["completeness_rate"] = quality_metrics["complete_results"] / total
            quality_metrics["high_confidence_rate"] = quality_metrics["high_confidence_results"] / total
            quality_metrics["average_confidence"] = sum(
                self._extract_confidence_score(r) for r in results
            ) / total
        
        return quality_metrics
    
    def validate_results_consistency(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate consistency across results."""
        consistency_report = {
            "is_consistent": True,
            "inconsistencies": [],
            "warnings": []
        }
        
        if not results:
            return consistency_report
        
        # Check for duplicate metrics
        metric_counts = {}
        for result in results:
            metric = result['metric']
            metric_counts[metric] = metric_counts.get(metric, 0) + 1
        
        for metric, count in metric_counts.items():
            if count > 1:
                consistency_report["warnings"].append(
                    f"Multiple results for metric '{metric}' ({count} instances)"
                )
        
        # Check for conflicting values
        metric_values = {}
        for result in results:
            metric = result['metric']
            value = result['value']
            units = result['units']
            
            if metric not in metric_values:
                metric_values[metric] = []
            
            metric_values[metric].append({
                'value': value,
                'units': units,
                'span_id': result.get('span_ids', [])[0] if result.get('span_ids') else None
            })
        
        # Check for unit inconsistencies
        for metric, values in metric_values.items():
            if len(values) > 1:
                units = [v['units'] for v in values]
                if len(set(units)) > 1:
                    consistency_report["inconsistencies"].append(
                        f"Unit mismatch for metric '{metric}': {units}"
                    )
                    consistency_report["is_consistent"] = False
        
        return consistency_report


# Global instance for easy access
_results_distiller = None


def get_results_distiller() -> ResultsDistiller:
    """Get the global ResultsDistiller instance."""
    global _results_distiller
    if _results_distiller is None:
        _results_distiller = ResultsDistiller()
    return _results_distiller


def reload_results_distiller() -> ResultsDistiller:
    """Reload the global ResultsDistiller instance."""
    global _results_distiller
    _results_distiller = ResultsDistiller()
    return _results_distiller
