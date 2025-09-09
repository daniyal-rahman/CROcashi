"""
Deterministic Results Distiller Worker

Extracts and normalizes results data using rule-based patterns, regex matching, and table parsing.
Provides an alternative to LLM-based extraction with high precision but potentially lower recall.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict

from ..base_worker import BaseWorker, WorkerResult
from ...models import EvidenceSpan, ResultsFactsheet
from ...models.results_factsheet import MetricType, UnitType, AnalysisSetType


class DeterministicResultsDistiller(BaseWorker):
    """
    Deterministic worker for extracting and normalizing results data from evidence spans.
    
    Uses rule-based patterns, regex matching, and table parsing to extract:
    - Response rates (ORR, CR, PR)
    - Survival metrics (OS, PFS, TTP)
    - Confidence intervals and p-values
    - Sample sizes and denominators
    """
    
    def __init__(self):
        super().__init__("DeterministicResultsDistiller", "1.0.0")
        
        # Pattern definitions for deterministic extraction
        self.response_patterns = {
            'orr': [
                r'orr\s*\(?recist\)?\s*[:=]\s*([\d\.]+)%',
                r'objective\s+response\s+rate\s*[:=]\s*([\d\.]+)%',
                r'overall\s+response\s+rate\s*[:=]\s*([\d\.]+)%'
            ],
            'cr': [
                r'complete\s+response\s*[:=]\s*([\d\.]+)%',
                r'cr\s*[:=]\s*([\d\.]+)%',
                r'complete\s+remission\s*[:=]\s*([\d\.]+)%'
            ],
            'pr': [
                r'partial\s+response\s*[:=]\s*([\d\.]+)%',
                r'pr\s*[:=]\s*([\d\.]+)%',
                r'partial\s+remission\s*[:=]\s*([\d\.]+)%'
            ]
        }
        
        self.survival_patterns = {
            'os': [
                r'median\s+os\s*=\s*([\d\.]+)\s*(weeks|months|years)',
                r'overall\s+survival\s*[:=]\s*([\d\.]+)\s*(weeks|months|years)',
                r'os\s*[:=]\s*([\d\.]+)\s*(weeks|months|years)'
            ],
            'pfs': [
                r'median\s+pfs\s*=\s*([\d\.]+)\s*(weeks|months|years)',
                r'progression.?free\s+survival\s*[:=]\s*([\d\.]+)\s*(weeks|months|years)',
                r'pfs\s*[:=]\s*([\d\.]+)\s*(weeks|months|years)'
            ],
            'ttp': [
                r'median\s+ttp\s*=\s*([\d\.]+)\s*(weeks|months|years)',
                r'time\s+to\s+progression\s*[:=]\s*([\d\.]+)\s*(weeks|months|years)',
                r'ttp\s*[:=]\s*([\d\.]+)\s*(weeks|months|years)'
            ]
        }
        
        self.confidence_interval_patterns = [
            r'\(([\d\.]+)\s*[-,]\s*([\d\.]+)\)',
            r'ci\s*[:=]\s*([\d\.]+)\s*[-,]\s*([\d\.]+)',
            r'confidence\s+interval\s*[:=]\s*([\d\.]+)\s*[-,]\s*([\d\.]+)'
        ]
        
        self.p_value_patterns = [
            r'p\s*[<=>]\s*([\d\.]+)',
            r'p.?value\s*[:=]\s*([\d\.]+)',
            r'p\s*[:=]\s*([\d\.]+)'
        ]
        
        self.sample_size_patterns = [
            r'n\s*=\s*(\d+)',
            r'sample\s+size\s*[:=]\s*(\d+)',
            r'(\d+)\s+patients',
            r'(\d+)\s+subjects'
        ]
    
    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Process evidence spans to extract normalized results data using deterministic rules.
        
        Args:
            inputs: Dict containing:
                - evidence_spans: List[EvidenceSpan] - Results/Abstract/Table spans
                - trial_context: Dict - Trial context information
                
        Returns:
            WorkerResult containing ResultsFactsheet
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required evidence_spans",
                    output={}
                )
            
            evidence_spans = inputs['evidence_spans']
            trial_context = inputs.get('trial_context', {})
            
            # Filter spans to focus on Results sections
            results_spans = self._filter_results_spans(evidence_spans)
            
            # Extract results data from spans using deterministic rules
            results_data = []
            for span in results_spans:
                span_results = self._extract_span_results_deterministic(span, trial_context)
                results_data.extend(span_results)
            
            # Deduplicate and merge results
            deduplicated_results = self._deduplicate_results(results_data)
            
            # Create ResultsFactsheet
            results_factsheet = self._create_results_factsheet(deduplicated_results, results_spans)
            
            return WorkerResult(
                success=True,
                output=results_factsheet,
                metadata={
                    'worker': 'DeterministicResultsDistiller',
                    'version': '1.0',
                    'processed_spans': len(results_spans),
                    'extracted_metrics': len(deduplicated_results)
                }
            )
            
        except Exception as e:
            return WorkerResult(
                success=False,
                error_message=f"Deterministic results distillation failed: {str(e)}",
                output={}
            )
    
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required evidence spans."""
        required_keys = ['evidence_spans']
        
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
    
    def _filter_results_spans(self, spans: List[EvidenceSpan]) -> List[EvidenceSpan]:
        """Filter spans to focus on Results/Abstract/Table sections."""
        results_sections = ['results', 'abstract', 'table']
        return [span for span in spans if span.section.lower() in results_sections]
    
    def _extract_span_results_deterministic(self, span: EvidenceSpan, 
                                           trial_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract results from a single span using deterministic patterns."""
        results = []
        text = span.quote.lower()
        
        # Extract response rates
        for metric_type, patterns in self.response_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # Check if we have enough groups before accessing them
                    if len(match.groups()) < 1:
                        continue
                    value = float(match.group(1))
                    results.append({
                        'metric': metric_type.upper(),
                        'value': value,
                        'unit': UnitType.PERCENT,
                        'timepoint': None,
                        'analysis_set': AnalysisSetType.NOT_SPECIFIED,
                        'n': self._extract_sample_size(text),
                        'ci_lower': None,
                        'ci_upper': None,
                        'p_value': None,
                        'span_ids': [span.span_id],
                        'section': span.section.title(),
                        'anchoring': self._get_anchoring(span),
                        'confidence': 0.90,
                        'source_path': 'deterministic'
                    })
                    break  # Take first match for each metric type
        
        # Extract survival metrics
        for metric_type, patterns in self.survival_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # Check if we have enough groups before accessing them
                    if len(match.groups()) < 2:
                        continue
                    value = float(match.group(1))
                    unit_text = match.group(2)
                    unit = self._normalize_unit(unit_text)
                    
                    # Extract confidence interval if present
                    ci_lower, ci_upper = self._extract_confidence_interval(text)
                    
                    # Extract p-value if present
                    p_value = self._extract_p_value(text)
                    
                    results.append({
                        'metric': metric_type.upper(),
                        'value': value,
                        'unit': unit,
                        'timepoint': None,
                        'analysis_set': AnalysisSetType.NOT_SPECIFIED,
                        'n': self._extract_sample_size(text),
                        'ci_lower': ci_lower,
                        'ci_upper': ci_upper,
                        'p_value': p_value,
                        'span_ids': [span.span_id],
                        'section': span.section.title(),
                        'anchoring': self._get_anchoring(span),
                        'confidence': 0.90,
                        'source_path': 'deterministic'
                    })
                    break  # Take first match for each metric type
        
        return results
    
    def _extract_sample_size(self, text: str) -> Optional[int]:
        """Extract sample size from text."""
        for pattern in self.sample_size_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None
    
    def _extract_confidence_interval(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        """Extract confidence interval from text."""
        for pattern in self.confidence_interval_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    lower = float(match.group(1))
                    upper = float(match.group(2))
                    return lower, upper
                except ValueError:
                    continue
        return None, None
    
    def _extract_p_value(self, text: str) -> Optional[float]:
        """Extract p-value from text."""
        for pattern in self.p_value_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None
    
    def _normalize_unit(self, unit_text: str) -> str:
        """Normalize unit text using shared TextNormalizer."""
        from ...utils.text_normalization import TextNormalizer
        normalized = TextNormalizer.normalize_unit(unit_text)
        # Map to the specific format expected by this worker
        if normalized in ['%', 'percent', 'percentage']:
            return 'percent'
        elif normalized in ['weeks', 'week', 'w']:
            return 'weeks'
        elif normalized in ['months', 'month', 'mo']:
            return 'months'
        elif normalized in ['years', 'year', 'yr']:
            return 'years'
        else:
            return 'not_specified'
    
    def _get_anchoring(self, span: EvidenceSpan) -> str:
        """Get anchoring information for the span."""
        if span.section.lower() == 'table':
            return 'table'
        elif span.section.lower() == 'results':
            return 'results_paragraph'
        elif span.section.lower() == 'abstract':
            return 'abstract'
        else:
            return 'unknown'
    
    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate results based on metric, timepoint, and analysis set."""
        # Group by metric to handle section-based deduplication
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
                # Use section-based precedence (Table > Results > Abstract)
                section_priority = {'table': 3, 'results': 2, 'abstract': 1}
                
                def get_section_priority(result):
                    section = result.get('section', '').lower()
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
                    # Multiple results in same section - take the first one
                    deduplicated.append(high_priority_results[0])
        
        return deduplicated
    
    def _create_results_factsheet(self, results: List[Dict[str, Any]], 
                                 spans: List[EvidenceSpan]) -> ResultsFactsheet:
        """Create ResultsFactsheet from extracted results."""
        # Get doc_id from spans or results
        doc_id = None
        if spans:
            doc_id = spans[0].doc_id
        elif results:
            doc_id = results[0].get('doc_id')
        
        if not doc_id:
            raise ValueError("Cannot create ResultsFactsheet without a valid doc_id from spans or results")
        
        # Convert results to ResultsFactsheet format
        results_list = []
        for result in results:
            result_item = {
                'metric': result['metric'],
                'value': result['value'],
                'unit': result['unit'],  # Use 'unit' for metric registry compatibility
                'span_ids': result['span_ids'],
                'n': result['n'],
                'ci_lower': result['ci_lower'],
                'ci_upper': result['ci_upper'],
                'p_value': result['p_value'],
                # Add missing fields needed for sorting with default values
                'analysis_set': result.get('analysis_set'),
                'timepoint': result.get('timepoint'),
                'is_posthoc': result.get('is_posthoc', False),
                'population_slice': result.get('population_slice'),
                'flags': result.get('flags', []),
                'section': result.get('section'),
                'doc_id': result.get('doc_id'),
            }
            
            # Centralize normalization using metric registry
            from ...normalization import get_metric_registry
            metric_registry = get_metric_registry()
            success, errors = metric_registry.normalize_metric_row(result_item)
            if not success:
                print(f"DEBUG: Deterministic normalization failed for {result_item['metric']}: {'; '.join(errors)}")
                # Continue without normalization rather than failing
            else:
                print(f"DEBUG: Deterministic normalized {result_item['metric']}: {result_item.get('value_normalized')} {result_item.get('unit_normalized', 'days')}")
            
            # Convert back to ResultsFactsheet format
            final_item = {
                'metric': result_item['metric'],
                'value': result_item['value'],
                'units': result_item['unit'],  # ResultsFactsheet expects 'units'
                'value_normalized': result_item.get('value_normalized'),
                'unit_normalized': result_item.get('unit_normalized'),
                'span_ids': result_item['span_ids'],
                'n': result_item['n'],
                'ci_lower': result_item['ci_lower'],
                'ci_upper': result_item['ci_upper'],
                'p_value': result_item['p_value'],
                'analysis_set': result_item.get('analysis_set'),
                'timepoint': result_item.get('timepoint'),
                'is_posthoc': result_item.get('is_posthoc', False),
                'population_slice': result_item.get('population_slice'),
                'flags': result_item.get('flags', []),
                'section': result_item.get('section'),
                'doc_id': result_item.get('doc_id'),
            }
            
            # Remove timepoint for median metrics
            if final_item['metric'] in {"median_ttp", "median_os", "median_pfs"}:
                final_item.pop("timepoint", None)
            
            results_list.append(final_item)
        
        return ResultsFactsheet(
            doc_id=doc_id,
            results=results_list
        )
