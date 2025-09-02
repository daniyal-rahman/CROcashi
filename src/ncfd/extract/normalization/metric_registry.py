"""
Metric Registry and Normalization Layer

Defines allowed metrics, units, and normalization rules for ResultsFactsheet.
Implements hard-fail validation for unit mismatches and missing required fields.
"""

from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import re
from decimal import Decimal, InvalidOperation


class MetricType(Enum):
    """Types of metrics supported by the registry."""
    SURVIVAL = "survival"
    RESPONSE = "response"
    BIOMARKER = "biomarker"
    SAFETY = "safety"
    PHARMACOKINETIC = "pharmacokinetic"
    EFFICACY = "efficacy"


class UnitType(Enum):
    """Types of units supported by the registry."""
    TIME = "time"
    PERCENTAGE = "percentage"
    COUNT = "count"
    CONCENTRATION = "concentration"
    DOSE = "dose"


@dataclass
class MetricDefinition:
    """Definition of a metric with its allowed units and normalization rules."""
    metric_id: str
    name: str
    metric_type: MetricType
    description: str
    allowed_units: List[str]
    default_unit: str
    normalize_to_unit: Optional[str] = None
    normalization_factor: Optional[float] = None
    required_fields: List[str] = field(default_factory=lambda: ["n", "value", "unit"])
    validation_rules: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate metric definition."""
        if self.default_unit not in self.allowed_units:
            raise ValueError(f"Default unit {self.default_unit} not in allowed units {self.allowed_units}")
        
        if self.normalize_to_unit and self.normalize_to_unit not in self.allowed_units:
            raise ValueError(f"Normalize to unit {self.normalize_to_unit} not in allowed units {self.allowed_units}")


@dataclass
class NormalizedValue:
    """A normalized value with its original and normalized representations."""
    original_value: Union[float, int]
    original_unit: str
    normalized_value: Optional[float] = None
    normalized_unit: Optional[str] = None
    normalization_factor: Optional[float] = None
    is_valid: bool = True
    error_message: Optional[str] = None


class MetricRegistry:
    """Registry for clinical trial metrics with validation and normalization."""
    
    def __init__(self):
        """Initialize the metric registry with oncology-specific metrics."""
        self.metrics: Dict[str, MetricDefinition] = {}
        self._initialize_oncology_metrics()
    
    def _initialize_oncology_metrics(self):
        """Initialize oncology-specific metrics."""
        # Survival metrics
        self.register_metric(MetricDefinition(
            metric_id="median_ttp",
            name="Median Time to Progression",
            metric_type=MetricType.SURVIVAL,
            description="Median time to disease progression",
            allowed_units=["weeks", "months", "days"],
            default_unit="weeks",
            normalize_to_unit="days",
            normalization_factor=7.0,  # weeks to days
            validation_rules={
                "min_value": 0,
                "max_value": 1000,
                "require_n": True
            }
        ))
        
        self.register_metric(MetricDefinition(
            metric_id="median_os",
            name="Median Overall Survival",
            metric_type=MetricType.SURVIVAL,
            description="Median overall survival time",
            allowed_units=["weeks", "months", "days"],
            default_unit="months",
            normalize_to_unit="days",
            normalization_factor=30.44,  # months to days (365.25/12)
            validation_rules={
                "min_value": 0,
                "max_value": 5000,
                "require_n": True
            }
        ))
        
        self.register_metric(MetricDefinition(
            metric_id="median_pfs",
            name="Median Progression-Free Survival",
            metric_type=MetricType.SURVIVAL,
            description="Median progression-free survival time",
            allowed_units=["weeks", "months", "days"],
            default_unit="months",
            normalize_to_unit="days",
            normalization_factor=30.44,  # months to days (365.25/12)
            validation_rules={
                "min_value": 0,
                "max_value": 5000,
                "require_n": True
            }
        ))
        
        # Response metrics
        self.register_metric(MetricDefinition(
            metric_id="orr_recist",
            name="Overall Response Rate (RECIST)",
            metric_type=MetricType.RESPONSE,
            description="Overall response rate by RECIST criteria",
            allowed_units=["%", "percent"],
            default_unit="%",
            normalize_to_unit="%",
            validation_rules={
                "min_value": 0,
                "max_value": 100,
                "require_n": True,
                "require_ci": False
            }
        ))
        
        self.register_metric(MetricDefinition(
            metric_id="ca125_response",
            name="CA-125 Response Rate",
            metric_type=MetricType.BIOMARKER,
            description="CA-125 response rate",
            allowed_units=["%", "percent"],
            default_unit="%",
            normalize_to_unit="%",
            validation_rules={
                "min_value": 0,
                "max_value": 100,
                "require_n": True,
                "require_ci": False
            }
        ))
        
        self.register_metric(MetricDefinition(
            metric_id="response_rate",
            name="Response Rate",
            metric_type=MetricType.RESPONSE,
            description="General response rate (non-RECIST)",
            allowed_units=["%", "percent"],
            default_unit="%",
            normalize_to_unit="%",
            validation_rules={
                "min_value": 0,
                "max_value": 100,
                "require_n": True,
                "require_ci": False
            }
        ))
        
        # Additional oncology metrics
        self.register_metric(MetricDefinition(
            metric_id="pfs_6m",
            name="6-Month Progression-Free Survival",
            metric_type=MetricType.SURVIVAL,
            description="6-month progression-free survival rate",
            allowed_units=["%", "percent"],
            default_unit="%",
            normalize_to_unit="%",
            validation_rules={
                "min_value": 0,
                "max_value": 100,
                "require_n": True
            }
        ))
        
        self.register_metric(MetricDefinition(
            metric_id="disease_control_rate",
            name="Disease Control Rate",
            metric_type=MetricType.RESPONSE,
            description="Disease control rate (CR+PR+SD)",
            allowed_units=["%", "percent"],
            default_unit="%",
            normalize_to_unit="%",
            validation_rules={
                "min_value": 0,
                "max_value": 100,
                "require_n": True
            }
        ))
    
    def register_metric(self, metric: MetricDefinition):
        """Register a new metric definition."""
        if metric.metric_id in self.metrics:
            raise ValueError(f"Metric {metric.metric_id} already registered")
        
        self.metrics[metric.metric_id] = metric
    
    def get_metric(self, metric_id: str) -> Optional[MetricDefinition]:
        """Get a metric definition by ID."""
        return self.metrics.get(metric_id)
    
    def list_metrics(self, metric_type: Optional[MetricType] = None) -> List[MetricDefinition]:
        """List all metrics, optionally filtered by type."""
        if metric_type is None:
            return list(self.metrics.values())
        
        return [m for m in self.metrics.values() if m.metric_type == metric_type]
    
    def validate_metric_value(self, metric_id: str, value: Union[float, int], 
                            unit: str, n: Optional[int] = None) -> Tuple[bool, List[str]]:
        """Validate a metric value against its definition."""
        metric = self.get_metric(metric_id)
        if not metric:
            return False, [f"Unknown metric: {metric_id}"]
        
        errors = []
        
        # Validate unit
        if unit not in metric.allowed_units:
            errors.append(f"Unit '{unit}' not allowed for metric {metric_id}. Allowed: {metric.allowed_units}")
        
        # Validate value range
        if "min_value" in metric.validation_rules:
            min_val = metric.validation_rules["min_value"]
            if value < min_val:
                errors.append(f"Value {value} below minimum {min_val} for metric {metric_id}")
        
        if "max_value" in metric.validation_rules:
            max_val = metric.validation_rules["max_value"]
            if value > max_val:
                errors.append(f"Value {value} above maximum {max_val} for metric {metric_id}")
        
        # Validate required fields
        if "require_n" in metric.validation_rules and metric.validation_rules["require_n"]:
            if n is None:
                errors.append(f"Sample size (n) required for metric {metric_id}")
            elif n <= 0:
                errors.append(f"Sample size (n) must be positive for metric {metric_id}")
        
        return len(errors) == 0, errors
    
    def normalize_value(self, metric_id: str, value: Union[float, int], 
                       unit: str) -> NormalizedValue:
        """Normalize a metric value to its standard unit."""
        metric = self.get_metric(metric_id)
        if not metric:
            return NormalizedValue(
                original_value=value,
                original_unit=unit,
                is_valid=False,
                error_message=f"Unknown metric: {metric_id}"
            )
        
        # Check if normalization is required
        if not metric.normalize_to_unit or unit == metric.normalize_to_unit:
            return NormalizedValue(
                original_value=value,
                original_unit=unit,
                normalized_value=value,
                normalized_unit=unit,
                is_valid=True
            )
        
        # Perform normalization
        try:
            # Always use _convert_units() which handles the from→to unit pair correctly
            normalized_value = self._convert_units(value, unit, metric.normalize_to_unit)
            
            return NormalizedValue(
                original_value=value,
                original_unit=unit,
                normalized_value=normalized_value,
                normalized_unit=metric.normalize_to_unit,
                is_valid=True
            )
            
        except Exception as e:
            return NormalizedValue(
                original_value=value,
                original_unit=unit,
                is_valid=False,
                error_message=f"Normalization failed: {str(e)}"
            )
    
    def _convert_units(self, value: Union[float, int], from_unit: str, to_unit: str) -> float:
        """Convert between common units."""
        # Normalize units to lowercase for comparison
        from_unit = from_unit.lower()
        to_unit = to_unit.lower()
        
        # Time conversions
        if from_unit == "weeks" and to_unit == "days":
            return value * 7.0
        elif from_unit == "months" and to_unit == "days":
            return value * 30.44  # 365.25/12
        elif from_unit == "years" and to_unit == "days":
            return value * 365.25
        elif from_unit == "hours" and to_unit == "days":
            return value / 24.0
        elif from_unit == "minutes" and to_unit == "days":
            return value / (24.0 * 60.0)
        
        # Percentage conversions
        elif from_unit == "percent" and to_unit == "%":
            return value
        elif from_unit == "%" and to_unit == "percent":
            return value
        
        # No conversion available
        raise ValueError(f"Cannot convert from {from_unit} to {to_unit}")
    
    def extract_metric_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract potential metrics from text using regex patterns."""
        extracted_metrics = []
        
        # Pattern for survival metrics - using named groups to handle different layouts
        survival_patterns = [
            # "median OS = 13.1 months"
            (re.compile(r"median\s+(?P<name>OS|overall\s+survival|PFS|progression[-\s]free\s+survival|TTP|time\s+to\s+progression)\s*[=:]\s*(?P<val>[\d\.]+)\s*(?P<unit>weeks?|months?|days?|years?)", re.I), "A"),
            # "13.1 months median OS"
            (re.compile(r"(?P<val>[\d\.]+)\s*(?P<unit>weeks?|months?|days?|years?)\s+median\s+(?P<name>OS|overall\s+survival|PFS|progression[-\s]free\s+survival|TTP|time\s+to\s+progression)", re.I), "B"),
        ]
        
        for rx, tag in survival_patterns:
            for m in rx.finditer(text):
                metric_id = self._map_survival_metric(m.group("name"))
                if not metric_id:
                    continue
                extracted_metrics.append({
                    "metric_id": metric_id,
                    "value": float(m.group("val")),
                    "unit": m.group("unit").lower(),
                    "text": m.group(0),
                    "confidence": 0.8
                })
        
        # Pattern for response rates
        response_patterns = [
            r"([\d\.]+)\s*%\s*(ORR|overall\s+response\s+rate|response\s+rate)",
            r"(ORR|overall\s+response\s+rate|response\s+rate)\s*[=:]\s*([\d\.]+)\s*%",
            r"(\d+)/(\d+)\s*\(([\d\.]+)%\)"  # n/N (percentage)
        ]
        
        for i, pattern in enumerate(response_patterns):
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                if i == 2:  # n/N format pattern (third pattern)
                    # Handle n/N format
                    n = int(match.group(1))
                    total = int(match.group(2))
                    percentage = float(match.group(3))
                    
                    extracted_metrics.append({
                        "metric_id": "orr_recist",
                        "value": percentage,
                        "unit": "%",
                        "n": n,
                        "total": total,
                        "text": match.group(0),
                        "confidence": 0.9
                    })
                else:
                    # Handle percentage format
                    matched_text = match.group(0).upper()
                    if "ORR" in matched_text or "OVERALL RESPONSE" in matched_text:
                        metric_id = "orr_recist"
                    else:
                        metric_id = "response_rate"
                    
                    value = float(match.group(1)) if match.group(1) else float(match.group(2))
                    
                    extracted_metrics.append({
                        "metric_id": metric_id,
                        "value": value,
                        "unit": "%",
                        "text": match.group(0),
                        "confidence": 0.8
                    })
        
        return extracted_metrics
    
    def _map_survival_metric(self, metric_name: str) -> Optional[str]:
        """Map survival metric names to metric IDs."""
        metric_lower = metric_name.lower()
        
        if any(term in metric_lower for term in ["ttp", "time to progression"]):
            return "median_ttp"
        elif any(term in metric_lower for term in ["os", "overall survival"]):
            return "median_os"
        elif any(term in metric_lower for term in ["pfs", "progression-free survival"]):
            return "median_pfs"
        else:
            return None
    
    def validate_results_factsheet(self, factsheet_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a complete ResultsFactsheet against the registry."""
        errors = []
        
        if "rows" not in factsheet_data:
            return False, ["ResultsFactsheet must contain 'rows' field"]
        
        for i, row in enumerate(factsheet_data["rows"]):
            row_errors = self._validate_factsheet_row(row, i)
            errors.extend(row_errors)
        
        return len(errors) == 0, errors
    
    def normalize_metric_row(self, row: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Normalize a single ResultsFactsheet row.
        
        Args:
            row: Dictionary containing metric data
            
        Returns:
            Tuple of (success, error_messages)
        """
        errors = []
        
        # Check required fields
        required_fields = ["metric", "value", "unit"]
        for field in required_fields:
            if field not in row:
                errors.append(f"Missing required field '{field}'")
        
        if errors:
            return False, errors
        
        # Validate metric exists in registry
        metric_id = row["metric"]
        metric = self.get_metric(metric_id)
        if not metric:
            errors.append(f"Unknown metric '{metric_id}'")
            return False, errors
        
        # Validate and normalize value
        try:
            value = float(row["value"])
            unit = row["unit"]
            
            # Validate the metric value
            n = int(row["n"]) if row.get("n") is not None else None
            is_valid, validation_errors = self.validate_metric_value(metric_id, value, unit, n)
            if not is_valid:
                errors.extend(validation_errors)
                return False, errors
            
            # Perform normalization if required
            if metric.normalize_to_unit:
                if unit != metric.normalize_to_unit:
                    # Unit conversion needed
                    normalized = self.normalize_value(metric_id, value, unit)
                    if not normalized.is_valid:
                        errors.append(normalized.error_message)
                        return False, errors
                    else:
                        # Add normalized values to row
                        row["value_normalized"] = normalized.normalized_value
                        row["unit_normalized"] = normalized.normalized_unit
                else:
                    # Input already in target unit, but ensure normalized fields are set for consistency
                    # This is especially important for survival metrics to ensure consistent output format
                    row["value_normalized"] = value
                    row["unit_normalized"] = unit
            
        except (ValueError, TypeError) as e:
            errors.append(f"Invalid value format: {str(e)}")
            return False, errors
        
        return True, errors
    
    def _validate_factsheet_row(self, row: Dict[str, Any], row_index: int) -> List[str]:
        """Validate a single ResultsFactsheet row (validation only, no normalization)."""
        errors = []
        row_prefix = f"Row {row_index + 1}:"
        
        # Check required fields
        required_fields = ["metric", "value", "unit", "n"]
        for field in required_fields:
            if field not in row:
                errors.append(f"{row_prefix} Missing required field '{field}'")
        
        if errors:
            return errors
        
        # Validate metric exists in registry
        metric_id = row["metric"]
        metric = self.get_metric(metric_id)
        if not metric:
            errors.append(f"{row_prefix} Unknown metric '{metric_id}'")
            return errors
        
        # Validate value and unit (validation only, no normalization)
        try:
            value = float(row["value"])
            unit = row["unit"]
            n = int(row["n"]) if row["n"] is not None else None
            
            is_valid, validation_errors = self.validate_metric_value(metric_id, value, unit, n)
            if not is_valid:
                errors.extend([f"{row_prefix} {error}" for error in validation_errors])
            
            # Check if normalization would be required (for validation purposes only)
            if metric.normalize_to_unit and unit != metric.normalize_to_unit:
                normalized = self.normalize_value(metric_id, value, unit)
                if not normalized.is_valid:
                    errors.append(f"{row_prefix} {normalized.error_message}")
                # Note: We don't add normalized values here - that's done by normalize_metric_row
            
        except (ValueError, TypeError) as e:
            errors.append(f"{row_prefix} Invalid value format: {str(e)}")
        
        return errors


# Global registry instance
_global_registry = None


def get_metric_registry() -> MetricRegistry:
    """Get the global metric registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = MetricRegistry()
    return _global_registry


def reload_metric_registry() -> MetricRegistry:
    """Reload the global metric registry."""
    global _global_registry
    _global_registry = MetricRegistry()
    return _global_registry
