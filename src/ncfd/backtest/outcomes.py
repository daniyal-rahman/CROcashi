"""
Outcome severity computation and grading.
"""

import math
import numpy as np
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple


@dataclass
class OutcomeSeverity:
    """Outcome severity result."""
    severity: float  # [0, 1] where 0 = success, 1 = fail
    grade: str       # SS, LS, A, LF, FF
    components: Dict[str, Any]  # Breakdown of computation
    confidence: float  # [0, 1] confidence in the assessment


def compute_outcome_severity(
    card: Dict[str, Any], 
    outcomes_cfg: Dict[str, Any]
) -> OutcomeSeverity:
    """
    Compute outcome severity from trial card.
    
    Args:
        card: Trial card data
        outcomes_cfg: Outcomes configuration
        
    Returns:
        OutcomeSeverity with severity, grade, and components
    """
    components = {}
    
    # Extract endpoint information
    endpoint = _extract_endpoint(card)
    endpoint_family = _classify_endpoint(endpoint, outcomes_cfg)
    
    # Compute base severity from effect size and p-value
    s_effect, s_p = _compute_base_severity(card, endpoint_family, outcomes_cfg)
    
    # Combine effect and p-value
    w_eff = outcomes_cfg["weights"]["effect"]
    w_p = outcomes_cfg["weights"]["pvalue"]
    
    vals, wts = [], []
    if s_effect is not None:
        vals.append(s_effect)
        wts.append(w_eff)
        components["effect_severity"] = s_effect
    if s_p is not None:
        vals.append(s_p)
        wts.append(w_p)
        components["pvalue_severity"] = s_p
    
    # Compute base severity
    if vals:
        s_base = np.average(vals, weights=wts)
        components["base_severity"] = s_base
    else:
        s_base = 0.5  # Default to ambiguous if no data
        components["base_severity"] = s_base
        components["note"] = "No effect size or p-value data available"
    
    # Apply robustness penalties
    penalties = _compute_penalties(card, outcomes_cfg)
    total_penalty = sum(penalties.values())
    s_final = max(0.0, min(1.0, s_base + total_penalty))
    
    components["penalties"] = penalties
    components["total_penalty"] = total_penalty
    components["final_severity"] = s_final
    
    # Determine grade
    grade = _severity_to_grade(s_final, outcomes_cfg["grades"])
    
    # Compute confidence
    confidence = _compute_confidence(vals, penalties, card)
    
    return OutcomeSeverity(
        severity=s_final,
        grade=grade,
        components=components,
        confidence=confidence
    )


def _extract_endpoint(card: Dict[str, Any]) -> Optional[str]:
    """Extract primary endpoint from card."""
    # Try multiple possible locations
    endpoint = (
        card.get("endpoint_ascertainment") or
        card.get("primary_endpoint") or
        card.get("method_card", {}).get("primary_endpoint")
    )
    return endpoint


def _classify_endpoint(endpoint: Optional[str], cfg: Dict[str, Any]) -> str:
    """Classify endpoint into family."""
    if not endpoint:
        return "continuous"  # Default
    
    endpoint_lower = endpoint.lower()
    
    # Time-to-event endpoints
    if any(term in endpoint_lower for term in ["survival", "time", "duration", "hr", "hazard"]):
        return "tte"
    
    # Binary endpoints
    if any(term in endpoint_lower for term in ["response", "remission", "cure", "binary", "rate"]):
        return "binary"
    
    # Default to continuous
    return "continuous"


def _compute_base_severity(
    card: Dict[str, Any], 
    endpoint_family: str, 
    cfg: Dict[str, Any]
) -> Tuple[Optional[float], Optional[float]]:
    """Compute base severity from effect size and p-value."""
    s_effect, s_p = None, None
    
    # Extract effect size and p-value
    primary_result = card.get("primary_result", {})
    itt_result = primary_result.get("ITT", {})
    
    effect = itt_result.get("estimate")
    p_value = itt_result.get("p")
    
    # Handle different endpoint families
    if endpoint_family == "continuous":
        s_effect, s_p = _continuous_severity(effect, p_value, card, cfg)
    elif endpoint_family == "binary":
        s_effect, s_p = _binary_severity(effect, p_value, card, cfg)
    elif endpoint_family == "tte":
        s_effect, s_p = _tte_severity(effect, p_value, card, cfg)
    
    return s_effect, s_p


def _continuous_severity(
    effect: Optional[float], 
    p_value: Optional[float], 
    card: Dict[str, Any], 
    cfg: Dict[str, Any]
) -> Tuple[Optional[float], Optional[float]]:
    """Compute severity for continuous endpoints."""
    s_effect, s_p = None, None
    
    if effect is not None:
        # Get MCID for this endpoint
        endpoint = _extract_endpoint(card)
        mcid = cfg["endpoints"]["continuous"]["mcid_lookup"].get(
            endpoint, 
            cfg["endpoints"]["continuous"]["sigma_default"] * 3
        )
        
        # Standardize effect (assume positive is favorable)
        d = effect / mcid
        z = d / cfg["endpoints"]["continuous"]["sigma_default"]
        s_effect = 1.0 / (1.0 + math.exp(z))  # sigmoid(-z)
    
    if p_value is not None:
        # Map p-value to severity (p < 0.05 is favorable)
        if p_value < 0.05:
            s_p = max(0.0, 1.0 - p_value / 0.05)  # Better p-value = lower severity
        else:
            s_p = min(1.0, p_value / 0.05)  # Worse p-value = higher severity
    
    return s_effect, s_p


def _binary_severity(
    effect: Optional[float], 
    p_value: Optional[float], 
    card: Dict[str, Any], 
    cfg: Dict[str, Any]
) -> Tuple[Optional[float], Optional[float]]:
    """Compute severity for binary endpoints."""
    s_effect, s_p = None, None
    
    if effect is not None:
        # For binary, assume effect is risk difference or log odds ratio
        # Standardize by default MCID
        mcid = cfg["endpoints"]["binary"]["mcid_abs_default"]
        d = abs(effect) / mcid
        z = d / cfg["endpoints"]["binary"]["sigma_default"]
        s_effect = 1.0 / (1.0 + math.exp(z))
    
    if p_value is not None:
        # Same p-value mapping as continuous
        if p_value < 0.05:
            s_p = max(0.0, 1.0 - p_value / 0.05)
        else:
            s_p = min(1.0, p_value / 0.05)
    
    return s_effect, s_p


def _tte_severity(
    effect: Optional[float], 
    p_value: Optional[float], 
    card: Dict[str, Any], 
    cfg: Dict[str, Any]
) -> Tuple[Optional[float], Optional[float]]:
    """Compute severity for time-to-event endpoints."""
    s_effect, s_p = None, None
    
    if effect is not None:
        # For TTE, assume effect is log hazard ratio
        # HR < 1 is favorable (lower hazard)
        d = -effect  # Flip sign so positive is favorable
        z = d / cfg["endpoints"]["tte"]["sigma_default"]
        s_effect = 1.0 / (1.0 + math.exp(z))
    
    if p_value is not None:
        # Same p-value mapping
        if p_value < 0.05:
            s_p = max(0.0, 1.0 - p_value / 0.05)
        else:
            s_p = min(1.0, p_value / 0.05)
    
    return s_effect, s_p


def _compute_penalties(card: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, float]:
    """Compute robustness penalties."""
    penalties = {}
    
    # Check for subgroup-only wins
    if _has_subgroup_only_wins(card):
        penalties["subgroup_only"] = cfg["penalties"]["subgroup_only"]
    
    # Check for non-ITT/PP analysis
    if _has_non_itt_analysis(card):
        penalties["non_itt_or_pp_only"] = cfg["penalties"]["non_itt_or_pp_only"]
    
    # Check for underpowered or missing primary result
    if _has_underpowered_or_no_primary(card):
        penalties["underpowered_or_no_primary"] = cfg["penalties"]["underpowered_or_no_primary"]
    
    # Check for endpoint change post-registration
    if _has_endpoint_change_post_reg(card):
        penalties["endpoint_changed_post_reg"] = cfg["penalties"]["endpoint_changed_post_reg"]
    
    # Check for non-significant results
    if _has_non_significant_result(card):
        penalties["non_significant"] = cfg["penalties"]["non_significant"]
    
    # Check for missing primary result
    if _has_missing_primary_result(card):
        penalties["missing_primary_result"] = cfg["penalties"]["missing_primary_result"]
    
    return penalties


def _has_subgroup_only_wins(card: Dict[str, Any]) -> bool:
    """Check if trial only has subgroup wins."""
    # Look for claims about subgroup-only significance
    claims = card.get("claims", [])
    for claim in claims:
        if "subgroup" in claim.get("proposition", "").lower():
            return True
    
    # Check if primary is not significant but subgroups are
    primary_result = card.get("primary_result", {})
    itt_result = primary_result.get("ITT", {})
    if itt_result.get("significant") is False:
        # Check if any subgroups are significant
        subgroups = card.get("subgroups", [])
        for subgroup in subgroups:
            if subgroup.get("significant") is True:
                return True
    
    return False


def _has_non_itt_analysis(card: Dict[str, Any]) -> bool:
    """Check if trial uses non-ITT analysis."""
    # Check ITT status
    itt_status = card.get("itt_status")
    if itt_status and itt_status.lower() not in ["itt", "modified itt", "mitt"]:
        return True
    
    # Check if only PP analysis is available
    primary_result = card.get("primary_result", {})
    if primary_result.get("ITT") is None and primary_result.get("PP") is not None:
        return True
    
    return False


def _has_underpowered_or_no_primary(card: Dict[str, Any]) -> bool:
    """Check if trial is underpowered or missing primary result."""
    # Check for claims about underpowered or missing primary
    claims = card.get("claims", [])
    for claim in claims:
        prop = claim.get("proposition", "").lower()
        if any(term in prop for term in ["underpowered", "no primary", "missing primary"]):
            return True
    
    # Check if primary result is missing
    primary_result = card.get("primary_result", {})
    if not primary_result.get("ITT") and not primary_result.get("PP"):
        return True
    
    return False


def _has_endpoint_change_post_reg(card: Dict[str, Any]) -> bool:
    """Check if endpoint was changed post-registration."""
    # Look for claims about endpoint changes
    claims = card.get("claims", [])
    for claim in claims:
        prop = claim.get("proposition", "").lower()
        if "endpoint" in prop and "change" in prop:
            return True
    
    return False


def _has_non_significant_result(card: Dict[str, Any]) -> bool:
    """Check if primary result is not significant."""
    primary_result = card.get("primary_result", {})
    itt_result = primary_result.get("ITT", {})
    return itt_result.get("significant") is False


def _has_missing_primary_result(card: Dict[str, Any]) -> bool:
    """Check if primary result is completely missing."""
    primary_result = card.get("primary_result", {})
    return not primary_result.get("ITT") and not primary_result.get("PP")


def _severity_to_grade(severity: float, grade_cfg: Dict[str, List[float]]) -> str:
    """Convert severity to grade."""
    for grade, bounds in grade_cfg.items():
        if bounds[0] <= severity <= bounds[1]:
            return grade
    
    # Fallback
    if severity <= 0.2:
        return "SS"
    elif severity <= 0.4:
        return "LS"
    elif severity <= 0.6:
        return "A"
    elif severity <= 0.8:
        return "LF"
    else:
        return "FF"


def _compute_confidence(
    severity_components: List[float], 
    penalties: Dict[str, float], 
    card: Dict[str, Any]
) -> float:
    """Compute confidence in the severity assessment."""
    # Base confidence on data availability
    confidence = 0.5  # Start at medium confidence
    
    # Boost confidence if we have effect size
    if severity_components:
        confidence += 0.3
    
    # Boost confidence if we have p-value
    if any("pvalue" in str(comp) for comp in severity_components):
        confidence += 0.2
    
    # Reduce confidence if many penalties
    if len(penalties) > 2:
        confidence -= 0.2
    
    # Reduce confidence if missing critical data
    if not card.get("primary_result"):
        confidence -= 0.3
    
    return max(0.0, min(1.0, confidence))
