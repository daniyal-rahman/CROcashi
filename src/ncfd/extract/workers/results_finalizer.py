"""
Results Finalizer Worker

Merges deterministic and LLM results into a canonical ResultsFactsheet.
Implements trust scoring, deduplication, and metadata preservation.
"""

import json
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import asdict
import logging

from .base_worker import BaseWorker, WorkerResult
from ..models import ResultsFactsheet
from ..models.llm_extraction_draft import LLMResultsDraft, EvidenceKind, EvidenceStatus
from ..models.results_factsheet import MetricType, UnitType, AnalysisSetType


class ResultsFinalizer(BaseWorker):
    """
    Worker for finalizing results by merging deterministic and LLM paths.
    
    Implements the final step of the LLM-first, provenance-second architecture:
    - Merges deterministic results (already have spans)
    - Merges LLM results (now have spans from Provenance Backtracer)
    - Deduplicates by metric/timepoint/slice
    - Applies trust scoring
    - Preserves metadata (verbatim quotes, etc.)
    """
    
    def __init__(self, 
                 prefer_deterministic_if_tie: bool = True,
                 min_provenance_score: float = 0.75,
                 hard_fail_if_missing_spans: bool = True,
                 base_trust_deterministic: float = 1.0,
                 base_trust_llm: float = 0.8):
        super().__init__("ResultsFinalizer", "1.0.0")
        
        self.prefer_deterministic_if_tie = prefer_deterministic_if_tie
        self.min_provenance_score = min_provenance_score
        self.hard_fail_if_missing_spans = hard_fail_if_missing_spans
        self.base_trust_deterministic = base_trust_deterministic
        self.base_trust_llm = base_trust_llm
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            h = logging.StreamHandler()
            fmt = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
            h.setFormatter(fmt)
            self.logger.addHandler(h)
        self.logger.setLevel(logging.INFO)

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """Validate that inputs contain required fields."""
        required_keys = ['doc_id']
        
        if not all(key in inputs for key in required_keys):
            return False
            
        if not isinstance(inputs['doc_id'], str):
            return False
            
        # At least one of deterministic_results or llm_results_draft should be present
        has_deterministic = 'deterministic_results' in inputs
        has_llm = 'llm_results_draft' in inputs
        
        if not has_deterministic and not has_llm:
            return False
            
        return True

    def process(self, inputs: Dict[str, Any]) -> WorkerResult:
        """
        Merge deterministic and LLM results into canonical ResultsFactsheet.
        
        Args:
            inputs: Dict containing:
                - doc_id: str - Document identifier
                - deterministic_results: ResultsFactsheet - Deterministic results (optional)
                - llm_results_draft: LLMResultsDraft - LLM results with spans (optional)
                - denominators: Dict - Denominator information (optional)
                
        Returns:
            WorkerResult containing canonical ResultsFactsheet
        """
        try:
            # Validate inputs
            if not self.validate_inputs(inputs):
                return WorkerResult(
                    success=False,
                    error_message="Invalid inputs: missing required doc_id or both result sets",
                    output={}
                )
            
            doc_id = inputs['doc_id']
            deterministic_results = inputs.get('deterministic_results')
            llm_results_draft = inputs.get('llm_results_draft')
            denominators = inputs.get('denominators', {})
            
            start_time = time.time()
            self.logger.info(f"Finalizing results for doc_id: {doc_id}")
            
            # Convert inputs to standardized format
            all_results = []
            
            # Add deterministic results
            if deterministic_results and deterministic_results.results:
                for result in deterministic_results.results:
                    standardized_result = self._standardize_deterministic_result(result)
                    all_results.append(standardized_result)
            
            # Add LLM results (if they have spans)
            if llm_results_draft and llm_results_draft.results:
                for i, result in enumerate(llm_results_draft.results):
                    # Only include LLM results that have resolved spans
                    if llm_results_draft.provenance_status[i] == "resolved":
                        standardized_result = self._standardize_llm_result(
                            result, llm_results_draft, i
                        )
                        all_results.append(standardized_result)
                    else:
                        self.logger.warning(f"Skipping LLM result {i} with unresolved provenance")
            
            # Deduplicate and merge results
            final_results = self._deduplicate_and_merge(all_results)
            
            # Apply denominator resolution
            final_results = self._apply_denominator_resolution(final_results, denominators)
            
            # Create canonical ResultsFactsheet
            results_factsheet = ResultsFactsheet(
                doc_id=doc_id,
                results=final_results
            )
            
            # Validate final results
            validation_result = self._validate_final_results(results_factsheet)
            if not validation_result['is_valid']:
                if self.hard_fail_if_missing_spans:
                    return WorkerResult(
                        success=False,
                        error_message=f"Validation failed: {validation_result['errors']}",
                        output={}
                    )
                else:
                    self.logger.warning(f"Validation warnings: {validation_result['warnings']}")
            
            self.logger.info(f"Finalized {len(final_results)} results")
            
            return WorkerResult(
                success=True,
                output={
                    'results_factsheet': results_factsheet,
                    'validation_result': validation_result,
                    'ambiguity_ledger': self._create_ambiguity_ledger(all_results)
                },
                execution_time=time.time() - start_time
            )
            
        except Exception as e:
            self.logger.error(f"Results finalization failed: {str(e)}")
            return WorkerResult(
                success=False,
                error_message=f"Results finalization failed: {str(e)}",
                output={}
            )

    def _standardize_deterministic_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Standardize deterministic result to final format."""
        return {
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
            'span_ids': result.get('span_ids', []),
            'source': 'deterministic',
            'provenance_score': 1.0,  # Deterministic results have perfect provenance
            'trust_score': self.base_trust_deterministic,
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
            'metadata': {
                'verbatim_quote': '',  # Deterministic results don't have quotes
                'evidence_kind': 'text',
                'section_hint': result.get('section', ''),
                'confidence_llm': 1.0
            }
        }

    def _standardize_llm_result(self, result: Dict[str, Any], 
                                llm_draft: LLMResultsDraft, index: int) -> Dict[str, Any]:
        """Standardize LLM result to final format."""
        # Apply definition vs result filter
        if self._is_definition_not_result(result, llm_draft, index):
            # Mark as definition and reduce confidence
            result['flags'] = result.get('flags', []) + ['definition_not_result']
            llm_draft.confidence_llm[index] *= 0.5  # Reduce confidence for definitions
        
        # Calculate provenance score based on backtracer results
        provenance_score = self._calculate_provenance_score(llm_draft, index)
        
        # Calculate trust score
        trust_score = self._calculate_trust_score(
            base_trust=self.base_trust_llm,
            provenance_score=provenance_score,
            confidence_llm=llm_draft.confidence_llm[index],
            result=result
        )
        
        return {
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
            'span_ids': [llm_draft.span_ids[index]] if llm_draft.span_ids[index] else [],
            'source': 'llm',
            'provenance_score': provenance_score,
            'trust_score': trust_score,
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
            'metadata': {
                'verbatim_quote': llm_draft.verbatim_quotes[index],
                'evidence_kind': llm_draft.evidence_kinds[index].value,
                'section_hint': llm_draft.section_hints[index],
                'table_hint': llm_draft.table_hints[index],
                'page_hint': llm_draft.page_hints[index],
                'confidence_llm': llm_draft.confidence_llm[index]
            }
        }

    def _calculate_provenance_score(self, llm_draft: LLMResultsDraft, index: int) -> float:
        """Calculate provenance score for LLM result."""
        if llm_draft.provenance_status[index] == "resolved":
            # Base score for resolved provenance
            base_score = 0.8
            
            # Boost for longer verbatim quotes
            quote_length = len(llm_draft.verbatim_quotes[index].split())
            if quote_length >= 10:
                base_score += 0.1
            elif quote_length >= 5:
                base_score += 0.05
            
            # Boost for results section
            if llm_draft.section_hints[index].lower() == 'results':
                base_score += 0.05
            
            # Boost for table evidence
            if llm_draft.evidence_kinds[index] == EvidenceKind.TABLE:
                base_score += 0.05
            
            return min(1.0, base_score)
        else:
            return 0.0

    def _calculate_trust_score(self, base_trust: float, provenance_score: float,
                              confidence_llm: float, result: Dict[str, Any]) -> float:
        """Calculate trust score for a result."""
        # Base trust score
        trust = base_trust
        
        # Adjust by provenance score
        trust *= provenance_score
        
        # Adjust by LLM confidence
        trust *= confidence_llm
        
        # Adjust by numeric sanity
        numeric_sanity = self._check_numeric_sanity(result)
        trust *= numeric_sanity
        
        # Adjust by metric importance
        metric_importance = self._get_metric_importance(result.get('metric', ''))
        trust *= metric_importance
        
        return min(1.0, max(0.0, trust))

    def _is_definition_not_result(self, result: Dict[str, Any], llm_draft: LLMResultsDraft, index: int) -> bool:
        """Check if a result is a definition rather than an observed outcome."""
        verbatim_quote = llm_draft.verbatim_quotes[index].lower()
        section_hint = llm_draft.section_hints[index].lower()
        metric = result.get('metric', '')
        
        # Check for definition keywords
        definition_keywords = [
            'defined as', 'criteria', 'was assessed using', 'per recist', 
            'threshold', 'definition', 'was defined', 'criterion'
        ]
        
        if any(keyword in verbatim_quote for keyword in definition_keywords):
            return True
        
        # Check for Methods section with definition-like content
        if section_hint == 'methods' and any(keyword in verbatim_quote for keyword in definition_keywords):
            return True
        
        # Specific check for CA-125 50% (common definition)
        if metric == 'ca125_response' and result.get('value') == 50.0:
            if 'defined' in verbatim_quote or 'threshold' in verbatim_quote:
                return True
        
        # Check for lack of result-like context
        result_keywords = ['observed', 'found', 'was', 'showed', 'revealed', 'patients', 'subjects']
        if not any(keyword in verbatim_quote for keyword in result_keywords):
            if section_hint == 'methods':
                return True
        
        return False

    def _check_numeric_sanity(self, result: Dict[str, Any]) -> float:
        """Check numeric sanity of result."""
        metric = result.get('metric', '')
        value = result.get('value')
        units = result.get('units', '')
        
        if value is None:
            return 0.5
        
        # Check for reasonable ranges
        if metric == 'orr_recist' and (value < 0 or value > 100):
            return 0.3
        
        if metric == 'median_os' and value < 0:
            return 0.3
        
        if metric == 'median_ttp' and value < 0:
            return 0.3
        
        # Check unit consistency
        if metric in ['orr_recist', 'ca125_response'] and units != 'percent':
            return 0.7
        
        if metric.startswith('median_') and units not in ['weeks', 'months', 'years']:
            return 0.7
        
        return 1.0

    def _get_metric_importance(self, metric: str) -> float:
        """Get importance multiplier for metric."""
        high_importance = ['orr_recist', 'median_os', 'median_ttp', 'ca125_response']
        medium_importance = ['median_pfs', 'hr', 'grade3_ae_rate']
        
        if metric in high_importance:
            return 1.0
        elif metric in medium_importance:
            return 0.9
        else:
            return 0.8

    def _deduplicate_and_merge(self, all_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate and merge results by metric/timepoint/slice."""
        # Group results by deduplication key
        grouped_results = {}
        
        for result in all_results:
            # Create deduplication key
            key = self._create_deduplication_key(result)
            
            if key not in grouped_results:
                grouped_results[key] = []
            grouped_results[key].append(result)
        
        # For each group, select the best result
        final_results = []
        
        for key, results in grouped_results.items():
            if len(results) == 1:
                # Single result, keep it
                final_results.append(results[0])
            else:
                # Multiple results, select the best one
                best_result = self._select_best_result(results)
                final_results.append(best_result)
        
        return final_results

    def _create_deduplication_key(self, result: Dict[str, Any]) -> str:
        """Create deduplication key for result."""
        metric = result.get('metric', '')
        timepoint = result.get('timepoint', '')
        population_slice = result.get('population_slice', '')
        
        return f"{metric}:{timepoint}:{population_slice}"

    def _select_best_result(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Select the best result from a group of duplicates."""
        # Sort by trust score (descending)
        sorted_results = sorted(results, key=lambda r: r.get('trust_score', 0), reverse=True)
        
        # If trust scores are tied, prefer deterministic
        if len(sorted_results) > 1:
            top_trust = sorted_results[0].get('trust_score', 0)
            top_results = [r for r in sorted_results if r.get('trust_score', 0) == top_trust]
            
            if len(top_results) > 1 and self.prefer_deterministic_if_tie:
                # Prefer deterministic results
                deterministic_results = [r for r in top_results if r.get('source') == 'deterministic']
                if deterministic_results:
                    return deterministic_results[0]
        
        return sorted_results[0]

    def _apply_denominator_resolution(self, results: List[Dict[str, Any]], 
                                     denominators: Any) -> List[Dict[str, Any]]:
        """Apply denominator resolution to results."""
        # Convert DenominatorResult to dictionary if needed
        if hasattr(denominators, 'response_n'):
            # It's a DenominatorResult object
            denominators_dict = {
                'orr_recist': denominators.response_n,
                'ca125_response': denominators.response_n,
                'median_ttp': denominators.ttp_os_n,
                'median_os': denominators.ttp_os_n,
                'median_pfs': denominators.ttp_os_n,
                'grade3_ae_rate': denominators.safety_n,
                'serious_ae_rate': denominators.safety_n
            }
        else:
            # It's already a dictionary
            denominators_dict = denominators or {}
        
        for result in results:
            metric = result.get('metric', '')
            
            # Check if denominator is missing
            if result.get('n') is None:
                # Try to find denominator from metadata
                metadata = result.get('metadata', {})
                verbatim_quote = metadata.get('verbatim_quote', '')
                
                # Extract denominator from quote (e.g., "3/19")
                extracted_n = self._extract_denominator_from_quote(verbatim_quote)
                if extracted_n:
                    result['n'] = extracted_n
                    result['flags'] = result.get('flags', []) + ['denominator_from_quote']
                else:
                    # Try to get from denominators dict
                    if metric in denominators_dict and denominators_dict[metric] is not None:
                        result['n'] = denominators_dict[metric]
                        result['flags'] = result.get('flags', []) + ['denominator_from_resolver']
        
        return results

    def _extract_denominator_from_quote(self, quote: str) -> Optional[int]:
        """Extract denominator from verbatim quote."""
        if not quote:
            return None
        
        # Look for patterns like "3/19", "15.8% (3/19)", etc.
        import re
        patterns = [
            r'(\d+)/(\d+)',  # "3/19"
            r'(\d+\.?\d*)%\s*\((\d+)/(\d+)\)',  # "15.8% (3/19)"
            r'(\d+)\s+of\s+(\d+)',  # "3 of 19"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, quote)
            if match:
                if len(match.groups()) == 2:
                    return int(match.group(2))  # Return denominator
                elif len(match.groups()) == 3:
                    return int(match.group(3))  # Return denominator from "15.8% (3/19)"
        
        return None

    def _validate_final_results(self, results_factsheet: ResultsFactsheet) -> Dict[str, Any]:
        """Validate final results."""
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        results = results_factsheet.results
        
        # Check for required metrics
        required_metrics = ['orr_recist', 'ca125_response']
        found_metrics = [r.get('metric') for r in results]
        
        missing_metrics = [m for m in required_metrics if m not in found_metrics]
        if missing_metrics:
            validation_result['warnings'].append(f"Missing required metrics: {missing_metrics}")
        
        # Check that all results have spans
        results_without_spans = [r for r in results if not r.get('span_ids')]
        if results_without_spans:
            if self.hard_fail_if_missing_spans:
                validation_result['is_valid'] = False
                validation_result['errors'].append(f"Results without spans: {len(results_without_spans)}")
            else:
                validation_result['warnings'].append(f"Results without spans: {len(results_without_spans)}")
        
        # Check provenance scores
        low_provenance_results = [r for r in results if r.get('provenance_score', 0) < self.min_provenance_score]
        if low_provenance_results:
            validation_result['warnings'].append(f"Results with low provenance: {len(low_provenance_results)}")
        
        return validation_result

    def _create_ambiguity_ledger(self, all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create ambiguity ledger for tracking conflicts."""
        ledger = {
            'denominator_conflicts': [],
            'metric_conflicts': [],
            'provenance_issues': []
        }
        
        # Track denominator conflicts
        metric_denominators = {}
        for result in all_results:
            metric = result.get('metric', '')
            n = result.get('n')
            source = result.get('source', '')
            
            if metric not in metric_denominators:
                metric_denominators[metric] = {}
            
            if n is not None:
                if n not in metric_denominators[metric]:
                    metric_denominators[metric][n] = []
                metric_denominators[metric][n].append(source)
        
        # Find conflicts
        for metric, denominators in metric_denominators.items():
            if len(denominators) > 1:
                ledger['denominator_conflicts'].append({
                    'metric': metric,
                    'denominators': denominators
                })
        
        return ledger
