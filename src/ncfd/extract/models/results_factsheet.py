"""
ResultsFactsheet Model

Represents normalized results data extracted from study results.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from .base import BaseModel, ProvenanceMixin


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
    PERCENT = "percent"
    COUNT = "count"
    RATIO = "ratio"


class AnalysisSetType(Enum):
    """Enum for analysis sets in ResultsFactsheet."""
    NOT_SPECIFIED = "not_specified"
    INTENT_TO_TREAT = "intent_to_treat"
    PER_PROTOCOL = "per_protocol"
    SAFETY = "safety"


@dataclass
class ResultsFactsheet(BaseModel, ProvenanceMixin):
    """Normalized results data with facts only."""
    
    # Array of result items
    results: List[Dict[str, Any]] = field(default_factory=list)
    
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
    
    def __post_init__(self):
        """Initialize provenance fields."""
        ProvenanceMixin.__init__(self)
        
        # Set default input_hash if not provided
        if not self.input_hash:
            import uuid
            self.input_hash = f"{uuid.uuid4().hex[:16]}"
    
    def validate(self) -> bool:
        """Validate the ResultsFactsheet."""
        if not self.results:
            return False
        
        # Validate each result
        for result in self.results:
            if not self._validate_result(result):
                return False
        
        return True
    
    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """Validate a single result item."""
        required_fields = ['metric', 'value', 'units', 'n', 'span_ids']
        
        # Check required fields
        for field in required_fields:
            if field not in result:
                print(f"DEBUG: Missing required field '{field}' in result")
                return False
        
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
        if not isinstance(result['n'], int) or result['n'] <= 0:
            print(f"DEBUG: n must be positive integer, got {result['n']}")
            return False
        
        # Validate span_ids
        if not isinstance(result['span_ids'], list) or len(result['span_ids']) == 0:
            print(f"DEBUG: span_ids must be non-empty list, got {result['span_ids']}")
            return False
        
        # Validate timepoint rule: only for fixed-time rates
        if 'timepoint' in result and result['timepoint'] is not None and result['metric'].startswith('median_'):
            print(f"DEBUG: Timepoint not allowed for median metrics: {result['metric']}")
            return False  # Reject timepoint with median metrics
        
        # Validate summary_statistic if present
        if 'summary_statistic' in result and result['summary_statistic'] not in ['median', 'proportion', 'mean', 'not_specified']:
            print(f"DEBUG: Invalid summary_statistic: {result['summary_statistic']}")
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
    
    def add_result(self, metric: str, value: Union[float, str], units: str, n: int,
                   ci_lower: Optional[float] = None, ci_upper: Optional[float] = None,
                   p_value: Optional[float] = None, direction: Optional[str] = None,
                   log_metric: Optional[float] = None, timepoint: Optional[str] = None,
                   analysis_set: Optional[str] = None, population_slice: Optional[str] = None,
                   is_posthoc: bool = False, flags: Optional[List[str]] = None,
                   span_ids: Optional[List[str]] = None, doc_id: Optional[str] = None,
                   method: Optional[str] = None, summary_statistic: Optional[str] = None,
                   range_min: Optional[float] = None, range_max: Optional[str] = None,
                   breakdown: Optional[Dict[str, int]] = None) -> None:
        """Add a result item with proper validation."""
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
        
        # Validate timepoint rule
        if timepoint and metric.startswith('median_'):
            raise ValueError(f"Timepoint not allowed for median metrics: {metric}")
        
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
            "doc_id": doc_id
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
