# src/ncfd/extract/models/results_factsheet.py
"""
ResultsFactsheet Model

Represents normalized results data extracted from study results.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from pydantic import model_validator, field_validator
from .base import BaseModel, ProvenanceMixin


def extract_doc_id_from_span_id(span_id: str) -> Optional[str]:
    """Extract doc_id from span_id format: {doc_id}#sec:{section}:char{start}-{end}"""
    try:
        if not isinstance(span_id, str):
            return None
        
        # Check if span_id has the expected format
        if '#' not in span_id or not span_id.startswith(span_id.split('#')[0] + '#sec:'):
            return None
        
        return span_id.split('#')[0]
    except (IndexError, AttributeError):
        return None


class MetricType(Enum):
    """Enum for metric types in ResultsFactsheet."""
    MEDIAN_OS = "median_os"
    MEDIAN_TTP = "median_ttp"
    MEDIAN_PFS = "median_pfs"
    ORR_RECIST = "orr_recist"
    CA125_RESPONSE = "ca125_response"
    OS_FIXED_TIME = "os_fixed_time"
    PFS_FIXED_TIME = "pfs_fixed_time"
    RESPONSE_RATE = "response_rate"
    HR = "hr"


class UnitType(Enum):
    """Enum for units in ResultsFactsheet."""
    MONTHS = "months"
    WEEKS = "weeks"
    DAYS = "days"
    PERCENT = "percent"
    COUNT = "count"
    RATIO = "ratio"


class AnalysisSetType(Enum):
    """Enum for analysis sets in ResultsFactsheet."""
    NOT_SPECIFIED = "not_specified"
    INTENT_TO_TREAT = "intent_to_treat"
    PER_PROTOCOL = "per_protocol"
    SAFETY = "safety"
    # Abbreviated forms for backward compatibility
    ITT = "ITT"
    PP = "PP"
    MITT = "mITT"


@dataclass
class ResultsFactsheet(BaseModel, ProvenanceMixin):
    """Normalized results data with facts only."""
    
    # Document identifier - now required
    doc_id: str = field(default="")  # Make it have a default to avoid dataclass ordering issues
    
    # Array of result items
    results: List[Dict[str, Any]] = field(default_factory=list)
    # Aggregated provenance across results
    span_ids: List[str] = field(default_factory=list)
    
    # Summary metadata
    primary_endpoint_results: Optional[Dict[str, Any]] = None
    secondary_endpoint_results: List[Dict[str, Any]] = field(default_factory=list)
    safety_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Analysis set information
    primary_analysis_set: Optional[str] = None  # ITT, mITT, PP
    secondary_analysis_sets: List[str] = field(default_factory=list)
    
    # Study completion information
    total_enrolled: Optional[int] = None
    completed_primary_endpoint: Optional[int] = None
    dropout_rate: Optional[float] = None
    follow_up_completion: Optional[float] = None
    
    @model_validator(mode='before')
    @classmethod
    def validate_doc_id(cls, values):
        """Ensure doc_id is always present and valid."""
        if isinstance(values, dict):
            doc_id = values.get('doc_id')
            if doc_id is None or doc_id == "":
                raise ValueError("doc_id is required and cannot be None or empty")
            if not isinstance(doc_id, str):
                raise ValueError(f"doc_id must be a string, got {type(doc_id)}")
            if not doc_id.strip():
                raise ValueError("doc_id cannot be empty or whitespace")
        return values
    
    @field_validator('doc_id')
    @classmethod
    def validate_doc_id_format(cls, v):
        """Validate doc_id format."""
        if not v or not isinstance(v, str) or v == "":
            raise ValueError(f"Invalid doc_id format: {v}")
        return v
    
    def __post_init__(self):
        """Initialize provenance fields."""
        ProvenanceMixin.__init__(self)
        
        # Set default input_hash if not provided
        if not self.input_hash:
            import uuid
            self.input_hash = f"{uuid.uuid4().hex[:16]}"
    
    def validate(self) -> bool:
        """Validate the ResultsFactsheet."""
        # Ensure doc_id is present
        if not self.doc_id:
            return False
        
        if not self.results:
            return False
        
        # Validate each result
        for result in self.results:
            if not self._validate_result(result):
                return False
        
        return True
    
    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """Validate a single result item."""
        required_fields = ['metric', 'value', 'units', 'span_ids']
        
        # Check required fields
        for field in required_fields:
            if field not in result:
                print(f"DEBUG: Missing required field '{field}' in result")
                return False
        
        # Check for survival median metrics that require normalized values
        survival_median_metrics = {MetricType.MEDIAN_OS.value, MetricType.MEDIAN_TTP.value, MetricType.MEDIAN_PFS.value}
        if result['metric'] in survival_median_metrics:
            if 'value_normalized' not in result:
                print(f"DEBUG: Survival median metric '{result['metric']}' requires value_normalized field")
                return False
            if 'unit_normalized' not in result:
                print(f"DEBUG: Survival median metric '{result['metric']}' requires unit_normalized field")
                return False
            
            # Validate normalized value is numeric
            if not isinstance(result['value_normalized'], (int, float)):
                print(f"DEBUG: value_normalized must be numeric, got {type(result['value_normalized'])}")
                return False
            
            # Validate normalized unit is days
            if result['unit_normalized'] != UnitType.DAYS.value:
                print(f"DEBUG: unit_normalized must be 'days' for survival median metrics, got {result['unit_normalized']}")
                return False
        
        # Check for pending denominator
        if result.get('pending_denominator', False):
            print(f"DEBUG: Result has pending denominator: {result['metric']}")
        
        # Validate metric enum
        try:
            MetricType(result['metric'])
        except ValueError as e:
            print(f"DEBUG: Invalid metric '{result['metric']}': {e}")
            return False
        
        # Validate units enum
        try:
            UnitType(result['units'])
        except ValueError as e:
            print(f"DEBUG: Invalid units '{result['units']}': {e}")
            return False
        
        # Validate numeric value
        if not isinstance(result['value'], (int, float)):
            print(f"DEBUG: Value must be numeric, got {type(result['value'])}")
            return False
        
        # Validate n (denominator)
        n_value = result.get('n')
        if result.get('pending_denominator', False):
            # Allow n to be None if pending_denominator is True
            if n_value is not None and (not isinstance(n_value, int) or n_value <= 0):
                print(f"DEBUG: pending_denominator=True but n invalid: {n_value}")
                return False
        else:
            # Require valid positive integer n when not pending
            if not isinstance(n_value, int) or n_value <= 0:
                print(f"DEBUG: n must be positive integer when not pending, got {n_value}")
                return False
        
        # Validate span_ids
        if not isinstance(result['span_ids'], list) or len(result['span_ids']) == 0:
            print(f"DEBUG: span_ids must be non-empty list, got {result['span_ids']}")
            return False
        
        # Validate that all span_ids are from the same document
        span_doc_ids = []
        for span_id in result['span_ids']:
            if not isinstance(span_id, str):
                print(f"DEBUG: span_id must be string, got {type(span_id)}")
                return False
            
            doc_id_from_span = extract_doc_id_from_span_id(span_id)
            if doc_id_from_span is None:
                print(f"DEBUG: Invalid span_id format '{span_id}', cannot extract doc_id")
                return False
            span_doc_ids.append(doc_id_from_span)
        
        # Check if all span_ids have the same doc_id
        if len(set(span_doc_ids)) > 1:
            print(f"DEBUG: All span_ids must be from the same document, got doc_ids: {list(set(span_doc_ids))}")
            return False
        
        # Validate doc_id consistency
        result_doc_id = result.get('doc_id')
        span_doc_id = span_doc_ids[0] if span_doc_ids else None
        
        if result_doc_id and span_doc_id and result_doc_id != span_doc_id:
            print(f"DEBUG: Result doc_id '{result_doc_id}' does not match span_ids doc_id '{span_doc_id}'")
            return False
        
        # If factsheet has doc_id, validate it matches
        if self.doc_id and span_doc_id and self.doc_id != span_doc_id:
            print(f"DEBUG: Factsheet doc_id '{self.doc_id}' does not match span_ids doc_id '{span_doc_id}'")
            return False
        
        # Validate timepoint rules
        if 'timepoint' in result and result['timepoint'] is not None and result['metric'].startswith('median_'):
            print(f"DEBUG: Timepoint not allowed for median metrics: {result['metric']}")
            return False  # Reject timepoint with median metrics
        if result['metric'] in (MetricType.OS_FIXED_TIME.value, MetricType.PFS_FIXED_TIME.value):
            if not result.get('timepoint'):
                print(f"DEBUG: {result['metric']} requires timepoint (e.g., 12_month)")
                return False
            # Validate timepoint format for fixed-time metrics
            import re
            timepoint_pattern = r"^\d+_(week|month|year)s?$"
            if not re.match(timepoint_pattern, result['timepoint']):
                print(f"DEBUG: Invalid timepoint format '{result['timepoint']}'. Expected format: number_unit (e.g., 12_month)")
                return False
        
        # Validate analysis_set if present
        if 'analysis_set' in result and result['analysis_set'] is not None:
            valid_analysis_sets = [e.value for e in AnalysisSetType]
            if result['analysis_set'] not in valid_analysis_sets:
                print(f"DEBUG: Invalid analysis_set '{result['analysis_set']}'. Must be one of {valid_analysis_sets}")
                return False
        
        # Validate summary_statistic if present
        if 'summary_statistic' in result:
            allowed_summary_stats = {'median', 'proportion', 'percentage', 'mean', 'hazard_ratio', 'not_specified', None}
            if result['summary_statistic'] not in allowed_summary_stats:
                print(f"DEBUG: Invalid summary_statistic: {result['summary_statistic']}")
                return False

        # HR-specific constraints
        if result['metric'] == MetricType.HR.value:
            if result['units'] != UnitType.RATIO.value:
                print(f"DEBUG: HR requires units='ratio', got {result['units']}")
                return False

        # Validate range_min/max numeric types if present
        if result.get('range_min') is not None and not isinstance(result.get('range_min'), (int, float)):
            print(f"DEBUG: range_min must be numeric, got {type(result.get('range_min'))}")
            return False
        if result.get('range_max') is not None and not isinstance(result.get('range_max'), (int, float)):
            print(f"DEBUG: range_max must be numeric, got {type(result.get('range_max'))}")
            return False
        
        # Validate breakdown if present
        if 'breakdown' in result and result['breakdown'] is not None:
            if not isinstance(result['breakdown'], dict):
                print(f"DEBUG: breakdown must be dict, got {type(result['breakdown'])}")
                return False
            for key, value in result['breakdown'].items():
                if not isinstance(value, int) or value < 0:
                    print(f"DEBUG: breakdown values must be non-negative integers, got {value}")
                    return False
        
        print(f"DEBUG: Result validation passed for {result['metric']}")
        return True
    
    def add_result(self, metric: str, value: Union[float, str], units: str, n: Optional[int],
                   ci_lower: Optional[float] = None, ci_upper: Optional[float] = None,
                   p_value: Optional[float] = None, direction: Optional[str] = None,
                   log_metric: Optional[float] = None, timepoint: Optional[str] = None,
                   analysis_set: Optional[str] = None, population_slice: Optional[str] = None,
                   is_posthoc: bool = False, flags: Optional[List[str]] = None,
                   span_ids: Optional[List[str]] = None, doc_id: Optional[str] = None,
                   method: Optional[str] = None, summary_statistic: Optional[str] = None,
                   range_min: Optional[float] = None, range_max: Optional[float] = None,
                   breakdown: Optional[Dict[str, int]] = None, pending_denominator: bool = False,
                   value_normalized: Optional[Union[float, str]] = None, unit_normalized: Optional[str] = None) -> None:
        """Add a result item with proper validation.
        
        Args:
            metric: The metric type
            value: The numeric value (will be coerced from string if needed)
            units: The units for the value
            n: The denominator/sample size
            value_normalized: The normalized value (required for survival median metrics, must be in days)
            unit_normalized: The normalized unit (required for survival median metrics, must be 'days')
            ... other parameters ...
        """
        # Coerce string value to float if needed
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                raise ValueError(f"Cannot convert value '{value}' to float for metric '{metric}'")
        
        # Validate metric enum
        try:
            MetricType(metric)
        except ValueError:
            raise ValueError(f"Invalid metric: {metric}. Must be one of {[m.value for m in MetricType]}")
        
        # Validate units enum
        try:
            UnitType(units)
        except ValueError:
            raise ValueError(f"Invalid units: {units}. Must be one of {[u.value for u in UnitType]}")
        
        # Validate timepoint rules pre-add
        if timepoint and metric.startswith('median_'):
            raise ValueError(f"Timepoint not allowed for median metrics: {metric}")
        if metric in (MetricType.OS_FIXED_TIME.value, MetricType.PFS_FIXED_TIME.value) and not timepoint:
            raise ValueError(f"{metric} requires timepoint (e.g., 12_month)")
        
        # Validate timepoint format for fixed-time metrics
        if metric in (MetricType.OS_FIXED_TIME.value, MetricType.PFS_FIXED_TIME.value) and timepoint:
            import re
            timepoint_pattern = r"^\d+_(week|month|year)s?$"
            if not re.match(timepoint_pattern, timepoint):
                raise ValueError(f"Invalid timepoint format '{timepoint}'. Expected format: number_unit (e.g., 12_month)")
        
        # Validate analysis_set if provided
        if analysis_set:
            valid_analysis_sets = [e.value for e in AnalysisSetType]
            if analysis_set not in valid_analysis_sets:
                raise ValueError(f"Invalid analysis_set '{analysis_set}'. Must be one of {valid_analysis_sets}")
        
        # Validate normalized fields for survival median metrics
        survival_median_metrics = {MetricType.MEDIAN_OS.value, MetricType.MEDIAN_TTP.value, MetricType.MEDIAN_PFS.value}
        if metric in survival_median_metrics:
            if value_normalized is None:
                raise ValueError(f"Survival median metric '{metric}' requires value_normalized")
            if unit_normalized is None:
                raise ValueError(f"Survival median metric '{metric}' requires unit_normalized")
            if unit_normalized != UnitType.DAYS.value:
                raise ValueError(f"unit_normalized must be 'days' for survival median metrics, got '{unit_normalized}'")
            
            # Coerce normalized value to float if needed
            if isinstance(value_normalized, str):
                try:
                    value_normalized = float(value_normalized)
                except ValueError:
                    raise ValueError(f"Cannot convert value_normalized '{value_normalized}' to float for metric '{metric}'")
        
        # Validate and set doc_id consistency
        if span_ids:
            span_doc_ids = []
            for span_id in span_ids:
                doc_id_from_span = extract_doc_id_from_span_id(span_id)
                if doc_id_from_span is None:
                    raise ValueError(f"Invalid span_id format '{span_id}', cannot extract doc_id")
                span_doc_ids.append(doc_id_from_span)
            
            # Check if all span_ids have the same doc_id
            if len(set(span_doc_ids)) > 1:
                raise ValueError(f"All span_ids must be from the same document, got doc_ids: {list(set(span_doc_ids))}")
            
            span_doc_id = span_doc_ids[0]
            
            # Set factsheet doc_id if not already set
            if self.doc_id is None:
                self.doc_id = span_doc_id
            elif self.doc_id != span_doc_id:
                raise ValueError(f"Factsheet doc_id '{self.doc_id}' does not match span_ids doc_id '{span_doc_id}'")
            
            # Set result doc_id if not provided
            if doc_id is None:
                doc_id = span_doc_id
            elif doc_id != span_doc_id:
                raise ValueError(f"Result doc_id '{doc_id}' does not match span_ids doc_id '{span_doc_id}'")
        
        result = {
            "metric": metric,
            "value": value,
            "units": units,
            "n": n,
            "method": method,
            "summary_statistic": summary_statistic,
            "range_min": range_min,
            "range_max": range_max,
            "breakdown": breakdown,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "p_value": p_value,
            "direction": direction,
            "log_metric": log_metric,
            "timepoint": timepoint,
            "analysis_set": analysis_set or self.primary_analysis_set,
            "population_slice": population_slice,
            "is_posthoc": is_posthoc,
            "flags": flags or [],
            "span_ids": span_ids or [],
            "doc_id": doc_id,
            "pending_denominator": pending_denominator,
            "value_normalized": value_normalized,
            "unit_normalized": unit_normalized
        }
        
        # Validate before adding
        if not self._validate_result(result):
            raise ValueError(f"Invalid result data: {result}")
        
        self.results.append(result)
        
        # Update summary fields
        if not is_posthoc and not population_slice:
            if metric.lower() in ["median_os", "median_ttp", "median_pfs"]:
                if not self.primary_endpoint_results:
                    self.primary_endpoint_results = result
                else:
                    self.secondary_endpoint_results.append(result)
        
        # Update span_ids with span_ids from this result
        if span_ids:
            for span_id in span_ids:
                if span_id not in self.span_ids:
                    self.span_ids.append(span_id)
    
    def get_primary_endpoint_result(self) -> Optional[Dict[str, Any]]:
        """Get the primary endpoint result."""
        return self.primary_endpoint_results
    
    def get_results_by_metric(self, metric: str) -> List[Dict[str, Any]]:
        """Get all results for a specific metric."""
        return [r for r in self.results if r["metric"].lower() == metric.lower()]
    
    def get_results_by_analysis_set(self, analysis_set: str) -> List[Dict[str, Any]]:
        """Get all results for a specific analysis set."""
        return [r for r in self.results if r["analysis_set"] == analysis_set]
    
    def get_posthoc_results(self) -> List[Dict[str, Any]]:
        """Get all post-hoc results."""
        return [r for r in self.results if r["is_posthoc"]]
    
    def get_subgroup_results(self) -> List[Dict[str, Any]]:
        """Get all subgroup results."""
        return [r for r in self.results if r["population_slice"]]
    
    def has_statistically_significant_result(self, metric: str) -> bool:
        """Check if there's a statistically significant result for a metric."""
        metric_results = self.get_results_by_metric(metric)
        return any(r.get("p_value", 1.0) < 0.05 for r in metric_results)
    
    def get_effect_size_summary(self) -> Dict[str, Any]:
        """Get a summary of effect sizes."""
        effect_sizes = {}
        for result in self.results:
            if result.get("value") is not None and isinstance(result["value"], (int, float)):
                metric = result["metric"]
                if metric not in effect_sizes:
                    effect_sizes[metric] = []
                effect_sizes[metric].append(result)
        return effect_sizes
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with all fields."""
        base_dict = super().to_dict()
        base_dict.update({
            "doc_id": self.doc_id,
            "results": self.results,
            "primary_endpoint_results": self.primary_endpoint_results,
            "secondary_endpoint_results": self.secondary_endpoint_results,
            "safety_results": self.safety_results,
            "primary_analysis_set": self.primary_analysis_set,
            "secondary_analysis_sets": self.secondary_analysis_sets,
            "total_enrolled": self.total_enrolled,
            "completed_primary_endpoint": self.completed_primary_endpoint,
            "dropout_rate": self.dropout_rate,
            "follow_up_completion": self.follow_up_completion
        })
        return base_dict
