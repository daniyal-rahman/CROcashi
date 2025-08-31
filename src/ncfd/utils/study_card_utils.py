"""
Study Card Utility Functions

Common utility functions for the study card system.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


def generate_span_id(doc_id: str, section: str, start_char: int, end_char: int, page: Optional[int] = None) -> str:
    """Generate a unique span ID.
    
    Args:
        doc_id: Document identifier
        section: Section name (Methods, Results, Table, etc.)
        start_char: Starting character position
        end_char: Ending character position
        page: Optional page number for additional context
        
    Returns:
        Span ID in format: {doc_id}#sec:{section}:char{start}-{end}
    """
    if page is not None:
        return f"{doc_id}#sec:{section}:char{start_char}-{end_char}:p{page}"
    return f"{doc_id}#sec:{section}:char{start_char}-{end_char}"


def generate_claim_id(prefix: str = "claim") -> str:
    """Generate a unique claim ID."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    random_suffix = hashlib.md5(f"{timestamp}".encode()).hexdigest()[:8]
    return f"{prefix}_{timestamp}_{random_suffix}"


def generate_gate_id(family: str = "g1") -> str:
    """Generate a unique gate ID."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    random_suffix = hashlib.md5(f"{timestamp}".encode()).hexdigest()[:8]
    return f"gate_{family}_{timestamp}_{random_suffix}"


def compute_input_hash(data: Any) -> str:
    """Compute a hash of input data for caching and lineage tracking."""
    if isinstance(data, (dict, list)):
        # Sort keys to ensure consistent hashing
        sorted_data = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(sorted_data.encode()).hexdigest()
    else:
        return hashlib.sha256(str(data).encode()).hexdigest()


def normalize_units(value: Union[str, float], from_units: str, to_units: str) -> Optional[float]:
    """Normalize units for comparison."""
    # Basic unit conversion mapping
    unit_conversions = {
        # Volume
        "ml": {"l": 0.001, "ul": 1000, "nl": 1000000},
        "l": {"ml": 1000, "ul": 1000000, "nl": 1000000000},
        "ul": {"ml": 0.001, "l": 0.000001, "nl": 1000},
        "nl": {"ml": 0.000001, "l": 0.000000001, "ul": 0.001},
        
        # Weight
        "mg": {"g": 0.001, "ug": 1000, "ng": 1000000},
        "g": {"mg": 1000, "ug": 1000000, "ng": 1000000000},
        "ug": {"mg": 0.001, "g": 0.000001, "ng": 1000},
        "ng": {"mg": 0.000001, "g": 0.000000001, "ug": 0.001},
        
        # Concentration
        "mg/ml": {"g/l": 1.0, "ug/ul": 1.0},
        "g/l": {"mg/ml": 1.0, "ug/ul": 1.0},
        "ug/ul": {"mg/ml": 1.0, "g/l": 1.0},
        
        # Time
        "min": {"hr": 1/60, "sec": 60},
        "hr": {"min": 60, "sec": 3600},
        "sec": {"min": 1/60, "hr": 1/3600}
    }
    
    if from_units == to_units:
        return float(value)
    
    if from_units in unit_conversions and to_units in unit_conversions[from_units]:
        conversion_factor = unit_conversions[from_units][to_units]
        return float(value) * conversion_factor
    
    # If no direct conversion, return None
    return None


def normalize_endpoint_name(endpoint: str) -> str:
    """Normalize endpoint names for comparison."""
    endpoint = endpoint.lower().strip()
    
    # Common endpoint mappings
    endpoint_mappings = {
        "overall survival": "os",
        "os": "os",
        "progression-free survival": "pfs",
        "pfs": "pfs",
        "disease-free survival": "dfs",
        "dfs": "dfs",
        "event-free survival": "efs",
        "efs": "efs",
        "response rate": "rr",
        "rr": "rr",
        "objective response rate": "orr",
        "orr": "orr",
        "complete response rate": "crr",
        "crr": "crr",
        "partial response rate": "prr",
        "prr": "prr"
    }
    
    return endpoint_mappings.get(endpoint, endpoint)


def extract_numeric_value(text: str) -> Optional[float]:
    """Extract numeric value from text."""
    import re
    
    # Look for common numeric patterns
    patterns = [
        r"(\d+\.?\d*)\s*%",  # Percentage
        r"(\d+\.?\d*)\s*(?:mg|g|ml|l|hr|min|sec)",  # With units
        r"(\d+\.?\d*)\s*(?:to|-)\s*(\d+\.?\d*)",  # Range
        r"(\d+\.?\d*)",  # Plain number
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            if isinstance(matches[0], tuple):
                # Range - take average
                values = [float(m) for m in matches[0]]
                return sum(values) / len(values)
            else:
                return float(matches[0])
    
    return None


def extract_confidence_interval(text: str) -> Optional[tuple]:
    """Extract confidence interval from text."""
    import re
    
    # Look for CI patterns like "95% CI: 1.2-3.4" or "1.2 (95% CI: 0.8-1.6)"
    ci_patterns = [
        r"(\d+\.?\d*)\s*\(95%\s*CI:\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\)",
        r"95%\s*CI:\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)",
        r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*\(95%\s*CI\)"
    ]
    
    for pattern in ci_patterns:
        matches = re.findall(pattern, text)
        if matches:
            if len(matches[0]) == 3:
                # Point estimate with CI
                return (float(matches[0][1]), float(matches[0][2]))
            elif len(matches[0]) == 2:
                # Just CI bounds
                return (float(matches[0][0]), float(matches[0][1]))
    
    return None


def extract_p_value(text: str) -> Optional[float]:
    """Extract p-value from text."""
    import re
    
    # Look for p-value patterns
    p_patterns = [
        r"p\s*[<≤]\s*(\d+\.?\d*)",
        r"p\s*=\s*(\d+\.?\d*)",
        r"(\d+\.?\d*)\s*\(p\s*[<≤]\s*(\d+\.?\d*)\)"
    ]
    
    for pattern in p_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            if isinstance(matches[0], tuple):
                return float(matches[0][1])
            else:
                return float(matches[0])
    
    return None


def calculate_effect_size(control_value: float, treatment_value: float, 
                         control_se: Optional[float] = None) -> Dict[str, float]:
    """Calculate effect size metrics."""
    effect_size = treatment_value - control_value
    relative_effect = (treatment_value - control_value) / control_value if control_value != 0 else 0
    
    result = {
        "absolute_effect": effect_size,
        "relative_effect": relative_effect
    }
    
    if control_se:
        # Calculate t-statistic
        t_stat = effect_size / control_se
        result["t_statistic"] = t_stat
        
        # Approximate Cohen's d
        cohens_d = effect_size / control_se
        result["cohens_d"] = cohens_d
    
    return result


def format_evidence_span(span: Dict[str, Any]) -> str:
    """Format an evidence span for display."""
    if "table_id" in span and span["table_id"]:
        return f"Table {span['table_id']}, page {span['page']}"
    elif "figure_id" in span and span["figure_id"]:
        return f"Figure {span['figure_id']}, page {span['page']}"
    else:
        return f"Page {span['page']}, lines {span['char_start']}-{span['char_end']}"


def validate_span_coordinates(page: int, start_char: int, end_char: int) -> bool:
    """Validate span coordinates."""
    if page < 1:
        return False
    if start_char < 0:
        return False
    if end_char <= start_char:
        return False
    return True


def merge_overlapping_spans(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge overlapping or adjacent spans."""
    if not spans:
        return []
    
    # Sort by page, then by start position
    sorted_spans = sorted(spans, key=lambda x: (x["page"], x["char_start"]))
    
    merged = []
    current = sorted_spans[0].copy()
    
    for span in sorted_spans[1:]:
        # Check if spans can be merged (same page and adjacent/overlapping)
        if (span["page"] == current["page"] and 
            span["char_start"] <= current["char_end"] + 1):
            # Merge spans
            current["char_end"] = max(current["char_end"], span["char_end"])
            current["quote"] = current["quote"] + " " + span["quote"]
        else:
            # Add current to merged list and start new current
            merged.append(current)
            current = span.copy()
    
    merged.append(current)
    return merged
