"""
S1-S9 Signal Detection Primitives

Implementation of the S1-S9 signal detection system based on the specifications
in docs/prompts/phase6.md.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime, date
import math

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    """Result of signal evaluation."""
    fired: bool
    severity: str  # "H", "M", "L"
    reason: str
    value: Optional[float] = None
    evidence_ids: Optional[List[str]] = None
    low_cert_inputs: Optional[List[str]] = None


def S1_endpoint_changed(trial_versions: List[Dict[str, Any]]) -> SignalResult:
    """
    S1 - Endpoint changed (material & late)
    
    Detects material endpoint changes that occur late in the trial lifecycle.
    """
    print(f"🚪 S1_SIGNAL: Called with {len(trial_versions) if trial_versions else 0} trial versions")
    print(f"🚪 S1_SIGNAL: Input trial_versions = {trial_versions}")
    
    if not trial_versions or len(trial_versions) < 2:
        result = SignalResult(False, "L", "Insufficient trial versions for comparison")
        print(f"🚪 S1_SIGNAL: Returning {result.fired}, {result.severity}, {result.reason}")
        return result
    
    # Sort versions by captured_at date
    sorted_versions = sorted(trial_versions, key=lambda v: v.get('captured_at', ''))
    
    material_changes = []
    evidence_ids = []
    
    for i in range(1, len(sorted_versions)):
        old_version = sorted_versions[i-1]
        new_version = sorted_versions[i]
        
        old_endpoint = old_version.get('primary_endpoint_text', '')
        new_endpoint = new_version.get('primary_endpoint_text', '')
        
        if not old_endpoint or not new_endpoint:
            continue
            
        # Check if change is material
        if _is_material_endpoint_change(old_endpoint, new_endpoint):
            # Check if change is late
            if _is_late_change(old_version, new_version):
                material_changes.append({
                    'old': old_endpoint,
                    'new': new_endpoint,
                    'change_date': new_version.get('captured_at'),
                    'completion_date': new_version.get('est_primary_completion_date')
                })
                evidence_ids.append(new_version.get('version_id', ''))
    
    if material_changes:
        # Determine severity based on timing
        latest_change = material_changes[-1]
        completion_date = latest_change.get('completion_date')
        
        severity = "H"  # Default to high severity for material late changes
        reason = f"Material endpoint change detected: '{latest_change['old']}' → '{latest_change['new']}'"
        
        return SignalResult(True, severity, reason, evidence_ids=evidence_ids)
    
    return SignalResult(False, "L", "No material late endpoint changes detected")


def S2_underpowered_pivotal(card: Dict[str, Any]) -> SignalResult:
    """
    S2 - Underpowered pivotal (<70% power at claimed Δ)
    
    Detects trials that are underpowered for their claimed effect size.
    """
    print(f"🚪 S2_SIGNAL: Called with card = {card}")
    print(f"🚪 S2_SIGNAL: is_pivotal = {card.get('is_pivotal', False)}")
    
    if not card.get("is_pivotal", False):
        result = SignalResult(False, "L", "Not a pivotal trial")
        print(f"🚪 S2_SIGNAL: Returning {result.fired}, {result.severity}, {result.reason}")
        return result
    
    analysis_plan = card.get("analysis_plan", {})
    primary_type = card.get("primary_type", "")
    
    if primary_type == "proportion":
        return _check_proportion_power(card, analysis_plan)
    elif primary_type == "tte":
        return _check_tte_power(card, analysis_plan)
    else:
        return SignalResult(False, "L", f"Unsupported primary type: {primary_type}")


def S3_subgroup_only_no_multiplicity(card: Dict[str, Any]) -> SignalResult:
    """
    S3 - Subgroup-only win without multiplicity adjustment
    """
    primary_result = card.get("primary_result", {})
    itt_result = primary_result.get("ITT", {})
    
    # If overall ITT is significant, no issue
    if itt_result.get("p", 1.0) < 0.05:
        return SignalResult(False, "L", "Overall ITT result is significant")
    
    subgroups = card.get("subgroups", [])
    flagged_subgroups = []
    
    for subgroup in subgroups:
        # Check for unadjusted significant subgroups
        if (subgroup.get("p", 1.0) < 0.05 and 
            not subgroup.get("adjusted", False) and
            not subgroup.get("pre_specified_interaction", False)):
            flagged_subgroups.append(subgroup.get("name", "Unknown"))
    
    if flagged_subgroups:
        severity = "H" if len(flagged_subgroups) > 1 else "M"
        reason = f"Subgroup-only wins without multiplicity adjustment: {', '.join(flagged_subgroups)}"
        return SignalResult(True, severity, reason, evidence_ids=[card.get("study_id", "")])
    
    return SignalResult(False, "L", "No unadjusted subgroup-only wins detected")


def S4_itt_vs_pp_dropout(card: Dict[str, Any]) -> SignalResult:
    """
    S4 - ITT neutral/negative vs PP positive + dropout asymmetry
    """
    primary_result = card.get("primary_result", {})
    itt = primary_result.get("ITT", {})
    pp = primary_result.get("PP", {})
    
    if not pp:
        return SignalResult(False, "L", "No per-protocol analysis available")
    
    arms = card.get("arms", {})
    treatment_arm = arms.get("t", {})
    control_arm = arms.get("c", {})
    
    drop_t = treatment_arm.get("dropout", 0)
    drop_c = control_arm.get("dropout", 0)
    asymmetry = abs(drop_t - drop_c)
    
    # Check conditions: ITT non-significant/negative AND PP significant/positive AND dropout asymmetry
    itt_non_sig = itt.get("p", 1.0) >= 0.05 or itt.get("estimate", 0) <= 0
    pp_sig = pp.get("p", 1.0) < 0.05 and pp.get("estimate", 0) > 0
    high_asymmetry = asymmetry >= 0.10
    
    if itt_non_sig and pp_sig and high_asymmetry:
        severity = "H" if asymmetry >= 0.20 else "M"
        reason = f"ITT/PP contradiction with dropout asymmetry: {asymmetry:.2f}"
        return SignalResult(True, severity, asymmetry, reason, [card.get("study_id", "")])
    
    return SignalResult(False, "L", "No ITT/PP contradiction with dropout asymmetry")


def S5_implausible_vs_graveyard(card: Dict[str, Any], class_meta: Dict[str, Any]) -> SignalResult:
    """
    S5 - Effect size >75th percentile of wins in "class graveyard"
    """
    if not class_meta.get("graveyard", False):
        return SignalResult(False, "L", "Class is not a graveyard")
    
    primary_result = card.get("primary_result", {})
    effect_size = primary_result.get("effect_size")
    
    if effect_size is None:
        return SignalResult(False, "L", "No effect size available")
    
    winners_pctl = class_meta.get("winners_pctl", {})
    p75 = winners_pctl.get("p75")
    
    if p75 is None:
        return SignalResult(False, "L", "No percentile data available")
    
    if effect_size >= p75:
        severity = "H" if effect_size >= p75 * 1.5 else "M"
        reason = f"Effect size {effect_size:.3f} ≥ P75 {p75:.3f} in graveyard class"
        return SignalResult(True, severity, effect_size, reason, [card.get("study_id", "")])
    
    return SignalResult(False, "L", "Effect size within plausible range")


def S6_many_interims_no_spending(card: Dict[str, Any]) -> SignalResult:
    """
    S6 - Multiple interim looks without alpha spending
    """
    analysis_plan = card.get("analysis_plan", {})
    planned_interims = analysis_plan.get("planned_interims", 0)
    alpha_spending = analysis_plan.get("alpha_spending")
    actual_peeks = card.get("actual_peeks", 0)
    
    # Check for multiple planned interims without alpha spending
    if planned_interims >= 2 and not alpha_spending:
        severity = "H" if planned_interims >= 3 else "M"
        reason = f"Multiple interim looks ({planned_interims}) without alpha spending"
        return SignalResult(True, severity, reason, [card.get("study_id", "")])
    
    # Check for extra data peeks
    extra_peeks = actual_peeks - planned_interims
    if extra_peeks > 0:
        reason = f"Extra data peeks ({extra_peeks}) without alpha reallocation"
        return SignalResult(True, "M", reason, [card.get("study_id", "")])
    
    return SignalResult(False, "L", "Interim control adequate")


def S7_single_arm_where_rct_standard(card: Dict[str, Any], rct_required: bool = False) -> SignalResult:
    """
    S7 - Single-arm where RCT is standard
    """
    if not card.get("is_pivotal", False):
        return SignalResult(False, "L", "Not a pivotal trial")
    
    if not card.get("single_arm", False):
        return SignalResult(False, "L", "Not a single-arm trial")
    
    if rct_required:
        reason = "Pivotal single-arm trial in setting where RCT is standard"
        return SignalResult(True, "H", reason, [card.get("study_id", "")])
    
    return SignalResult(False, "L", "Single-arm acceptable per precedent")


def S8_pvalue_cusp_or_heaping(card: Dict[str, Any], program_pvals: Optional[List[float]] = None) -> SignalResult:
    """
    S8 - P-value cusp 0.045-0.050 or heaping
    """
    primary_result = card.get("primary_result", {})
    p_value = primary_result.get("ITT", {}).get("p")
    
    if p_value is None:
        return SignalResult(False, "L", "No p-value available")
    
    # Check for cusp region
    if 0.045 <= p_value <= 0.050:
        reason = f"Primary p-value in cusp region: {p_value:.4f}"
        return SignalResult(True, "M", p_value, reason, [card.get("study_id", "")])
    
    # Check for heaping in program-level p-values
    if program_pvals:
        for pval in program_pvals:
            if pval < 0.01:
                # Check for heaping pattern (simplified)
                reason = f"Potential p-value heaping detected: {pval:.4f}"
                return SignalResult(True, "H", pval, reason, [card.get("study_id", "")])
    
    return SignalResult(False, "L", "No cusp or heaping detected")


def S9_os_pfs_contradiction(card: Dict[str, Any]) -> SignalResult:
    """
    S9 - OS/PFS contradiction (context-dependent)
    """
    pfs = card.get("pfs", {})
    os = card.get("os", {})
    
    if not pfs or not os:
        return SignalResult(False, "L", "Missing PFS or OS endpoints")
    
    # Check for PFS positive and OS harmful
    pfs_pos = (pfs.get("p", 1.0) < 0.05) or (pfs.get("hr", 1.0) < 1 and pfs.get("ci95_upper", 1.01) < 1)
    os_harm = (os.get("hr", 1.0) >= 1.10) and (os.get("events_frac", 0) >= 0.60) and (os.get("p", 1.0) < 0.20)
    
    if pfs_pos and os_harm:
        reason = "PFS positive but OS shows potential harm"
        return SignalResult(True, "H", reason, [card.get("study_id", "")])
    
    return SignalResult(False, "L", "No OS/PFS contradiction detected")


# Helper functions

def _is_material_endpoint_change(old_endpoint: str, new_endpoint: str) -> bool:
    """Check if endpoint change is material."""
    old_lower = old_endpoint.lower()
    new_lower = new_endpoint.lower()
    
    # Check for major endpoint type changes
    endpoint_types = ['pfs', 'os', 'orr', 'pro', 'dfs', 'efs']
    
    old_type = None
    new_type = None
    
    for endpoint_type in endpoint_types:
        if endpoint_type in old_lower:
            old_type = endpoint_type
        if endpoint_type in new_lower:
            new_type = endpoint_type
    
    # Material if endpoint type changed
    if old_type and new_type and old_type != new_type:
        return True
    
    # Check for objective/subjective changes
    if ('objective' in old_lower and 'subjective' in new_lower) or \
       ('subjective' in old_lower and 'objective' in new_lower):
        return True
    
    # Check for superiority/non-inferiority changes
    if ('superiority' in old_lower and 'non-inferiority' in new_lower) or \
       ('non-inferiority' in old_lower and 'superiority' in new_lower):
        return True
    
    # Check for blinded/unblinded changes
    if ('blinded' in old_lower and 'unblinded' in new_lower) or \
       ('unblinded' in old_lower and 'blinded' in new_lower):
        return True
    
    return False


def _is_late_change(old_version: Dict[str, Any], new_version: Dict[str, Any]) -> bool:
    """Check if change occurred late in trial lifecycle."""
    change_date_str = new_version.get('captured_at', '')
    completion_date_str = new_version.get('est_primary_completion_date', '')
    
    if not change_date_str or not completion_date_str:
        return False
    
    try:
        change_date = datetime.fromisoformat(change_date_str.replace('Z', '+00:00')).date()
        completion_date = datetime.fromisoformat(completion_date_str.replace('Z', '+00:00')).date()
        
        # Check if change occurred within 180 days of completion
        days_to_completion = (completion_date - change_date).days
        return days_to_completion <= 180
        
    except (ValueError, TypeError):
        return False


def _check_proportion_power(card: Dict[str, Any], analysis_plan: Dict[str, Any]) -> SignalResult:
    """Check power for proportion-based endpoints."""
    arms = card.get("arms", {})
    n_t = arms.get("t", {}).get("n", 0)
    n_c = arms.get("c", {}).get("n", 0)
    
    if n_t == 0 or n_c == 0:
        return SignalResult(False, "L", "Missing sample size data")
    
    alpha = analysis_plan.get("alpha", 0.05)
    one_sided = analysis_plan.get("one_sided", False)
    assumed_p_c = analysis_plan.get("assumed_p_c", 0.5)
    assumed_delta = analysis_plan.get("assumed_delta_abs", 0.1)
    
    # Calculate power (simplified)
    # This is a placeholder - real implementation would use proper power calculation
    power = 0.65  # Placeholder - would calculate actual power
    
    if power < 0.70:
        reason = f"Underpowered: {power:.2f} < 0.70 at assumed delta {assumed_delta:.2f}"
        return SignalResult(True, "H", power, reason, [card.get("study_id", "")])
    
    return SignalResult(False, "L", f"Adequate power: {power:.2f}")


def _check_tte_power(card: Dict[str, Any], analysis_plan: Dict[str, Any]) -> SignalResult:
    """Check power for time-to-event endpoints."""
    arms = card.get("arms", {})
    n_t = arms.get("t", {}).get("n", 0)
    n_c = arms.get("c", {}).get("n", 0)
    
    if n_t == 0 or n_c == 0:
        return SignalResult(False, "L", "Missing sample size data")
    
    alpha = analysis_plan.get("alpha", 0.05)
    hr_alt = analysis_plan.get("hr_alt", 0.8)
    planned_events = analysis_plan.get("planned_events", 100)
    
    # Calculate power (simplified)
    # This is a placeholder - real implementation would use proper power calculation
    power = 0.65  # Placeholder - would calculate actual power
    
    if power < 0.70:
        reason = f"Underpowered: {power:.2f} < 0.70 at HR_alt {hr_alt:.2f}, events {planned_events}"
        return SignalResult(True, "H", power, reason, [card.get("study_id", "")])
    
    return SignalResult(False, "L", f"Adequate power: {power:.2f}")
