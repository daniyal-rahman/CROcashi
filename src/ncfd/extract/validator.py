"""
Study Card validation and pivotal gate enforcement.

This module provides validation for Study Card JSON against the schema
and enforces pivotal trial requirements.
"""

from __future__ import annotations
import json
import jsonschema
from pathlib import Path
from typing import Dict, Any, List


def load_schema() -> Dict[str, Any]:
    """Load the Study Card JSON schema."""
    try:
        # Try to load from the package
        import importlib.resources as resources
        schema_text = resources.files("ncfd.extract").joinpath("study_card.schema.json").read_text()
        return json.loads(schema_text)
    except (ImportError, FileNotFoundError):
        # Fallback to direct file path
        schema_path = Path(__file__).parent / "study_card.schema.json"
        with open(schema_path, 'r') as f:
            return json.load(f)


# Load schema once at module level
_schema = load_schema()


def validate_card(card: Dict[str, Any], is_pivotal: bool = False) -> None:
    """
    Validate a Study Card against the schema and pivotal requirements.
    
    Args:
        card: Study Card dictionary to validate
        is_pivotal: Whether this is a pivotal trial
        
    Raises:
        jsonschema.ValidationError: If schema validation fails
        ValueError: If pivotal trial requirements are not met
    """
    # First, validate against JSON schema
    jsonschema.validate(card, _schema)
    
    # Check pivotal trial requirements
    if is_pivotal:
        missing = _check_pivotal_requirements(card)
        if missing:
            raise ValueError(f"PivotalStudyMissingFields: {', '.join(missing)}")


def _check_pivotal_requirements(card: Dict[str, Any]) -> List[str]:
    """
    Check if a pivotal trial card meets all required fields.
    
    Args:
        card: Validated Study Card dictionary
        
    Returns:
        List of missing required field paths
    """
    missing = []
    
    # Check primary endpoints
    if not card.get("primary_endpoints"):
        missing.append("primary_endpoints")
    
    # Check sample size total N
    total_n = ((card.get("sample_size") or {}).get("total_n"))
    if total_n is None:
        missing.append("sample_size.total_n")
    
    # Check ITT/PP selection for primary analysis
    if not (card.get("populations") or {}).get("analysis_primary_on"):
        missing.append("populations.analysis_primary_on")
    
    # Check effect size OR p-value for primary endpoint
    ok = False
    for r0 in (card.get("results") or {}).get("primary", []):
        eff = (r0.get("effect_size") or {}).get("value")
        p = r0.get("p_value")
        if eff is not None or p is not None:
            ok = True
            break
    
    if not ok:
        missing.append("results.primary.(effect_size.value OR p_value)")
    
    return missing


def validate_evidence_spans(card: Dict[str, Any]) -> List[str]:
    """
    Validate that all numeric claims have evidence spans.
    
    Args:
        card: Study Card dictionary
        
    Returns:
        List of validation issues found
    """
    issues = []
    
    # Helper function to check evidence
    def has_evidence(obj: Dict[str, Any], field_name: str) -> bool:
        """Check if an object has evidence spans."""
        evidence = obj.get("evidence", [])
        return isinstance(evidence, list) and len(evidence) > 0
    
    # Check primary endpoints
    for i, endpoint in enumerate(card.get("primary_endpoints", [])):
        if not has_evidence(endpoint, "evidence"):
            issues.append(f"primary_endpoints[{i}].evidence")
    
    # Check sample size
    sample_size = card.get("sample_size", {})
    if sample_size.get("total_n") is not None and not has_evidence(sample_size, "evidence"):
        issues.append("sample_size.evidence")
    
    # Check arms
    for i, arm in enumerate(card.get("arms", [])):
        if arm.get("n") is not None and not has_evidence(arm, "evidence"):
            issues.append(f"arms[{i}].evidence")
    
    # Check results
    for i, result in enumerate(card.get("results", {}).get("primary", [])):
        if result.get("p_value") is not None and not has_evidence(result, "evidence"):
            issues.append(f"results.primary[{i}].evidence")
        
        effect_size = result.get("effect_size", {})
        if effect_size.get("value") is not None and not has_evidence(effect_size, "evidence"):
            issues.append(f"results.primary[{i}].effect_size.evidence")
    
    return issues


def get_coverage_level(card: Dict[str, Any]) -> str:
    """
    Determine the coverage level based on card content.
    
    Args:
        card: Study Card dictionary
        
    Returns:
        Coverage level: "high", "med", or "low"
    """
    # Check required elements for high coverage
    has_primary_endpoint = bool(card.get("primary_endpoints"))
    has_total_n = card.get("sample_size", {}).get("total_n") is not None
    has_analysis_population = bool(card.get("populations", {}).get("analysis_primary_on"))
    
    # Check for effect size or p-value
    has_effect_or_p = False
    for result in card.get("results", {}).get("primary", []):
        if (result.get("effect_size", {}).get("value") is not None or 
            result.get("p_value") is not None):
            has_effect_or_p = True
            break
    
    # Count missing elements
    missing_count = 0
    if not has_primary_endpoint:
        missing_count += 1
    if not has_total_n:
        missing_count += 1
    if not has_analysis_population:
        missing_count += 1
    if not has_effect_or_p:
        missing_count += 1
    
    # Determine coverage level
    if missing_count == 0:
        return "high"
    elif missing_count == 1:
        return "med"
    else:
        return "low"


def validate_card_completeness(card: Dict[str, Any]) -> Dict[str, Any]:
    """
    Comprehensive validation of a Study Card.
    
    Args:
        card: Study Card dictionary
        
    Returns:
        Dictionary with validation results and recommendations
    """
    results = {
        "is_valid": True,
        "schema_errors": [],
        "pivotal_errors": [],
        "evidence_issues": [],
        "coverage_level": "unknown",
        "recommendations": []
    }
    
    try:
        # Schema validation
        jsonschema.validate(card, _schema)
        results["coverage_level"] = get_coverage_level(card)
    except jsonschema.ValidationError as e:
        results["is_valid"] = False
        results["schema_errors"].append(str(e))
    
    # Check pivotal requirements if applicable
    is_pivotal = card.get("trial", {}).get("is_pivotal", False)
    if is_pivotal:
        try:
            missing = _check_pivotal_requirements(card)
            if missing:
                results["pivotal_errors"] = missing
                results["recommendations"].append("Pivotal trial missing required fields")
        except ValueError as e:
            results["pivotal_errors"].append(str(e))
    
    # Check evidence spans
    evidence_issues = validate_evidence_spans(card)
    if evidence_issues:
        results["evidence_issues"] = evidence_issues
        results["recommendations"].append("Add evidence spans for all numeric claims")
    
    # Generate recommendations
    if results["coverage_level"] == "low":
        results["recommendations"].append("Consider manual review due to low coverage")
    
    if not results["is_valid"]:
        results["recommendations"].append("Fix schema validation errors first")
    
    return results
