"""
Gates G1-G4 for precision-first failure detection.

Composes primitive signals (S1-S9) into higher-level failure modes.
Specification from global_prompt.md:
- G1 Alpha-Meltdown = S1 & S2
- G2 Analysis-Gaming = S3 & S4  
- G3 Plausibility = S5 & (S7 | S6)
- G4 p-Hacking = S8 & (S1 | S3)
"""

import math
from typing import Dict, List, Optional
from .types import GateResult, SignalResult


def G1_alpha_meltdown(signals: Dict[str, SignalResult]) -> GateResult:
    """
    G1: Alpha-Meltdown = S1 & S2
    
    Requires BOTH endpoint change (S1) AND underpowered pivotal (S2).
    """
    s1 = signals.get("S1")
    s2 = signals.get("S2")
    
    # Check for insufficient inputs
    if s1 is None or s2 is None or s1.fired is None or s2.fired is None:
        missing = []
        if s1 is None or s1.fired is None:
            missing.append("S1")
        if s2 is None or s2.fired is None:
            missing.append("S2")
        return GateResult(
            id="G1",
            fired=False,
            status="insufficient_inputs",
            rationale=f"Missing required inputs: {', '.join(missing)}"
        )
    
    fired = s1.fired and s2.fired
    
    if not fired:
        return GateResult(
            id="G1",
            fired=False,
            rationale="Alpha-Meltdown requires both S1 (endpoint change) and S2 (underpowered)"
        )
    
    # Build rationale with evidence
    rationale_parts = ["Alpha-Meltdown: Both S1 (endpoint change) and S2 (underpowered) fired"]
    supporting_signals = ["S1", "S2"]
    
    if s1.value is not None:
        rationale_parts.append(f"S1 value: {s1.value}")
    if s2.value is not None:
        rationale_parts.append(f"S2 value: {s2.value}")
    
    return GateResult(
        id="G1",
        fired=True,
        supporting_signals=supporting_signals,
        rationale="; ".join(rationale_parts)
    )


def G2_analysis_gaming(signals: Dict[str, SignalResult]) -> GateResult:
    """
    G2: Analysis-Gaming = S3 & S4
    
    Requires BOTH subgroup-only win (S3) AND ITT/PP dropout asymmetry (S4).
    """
    s3 = signals.get("S3")
    s4 = signals.get("S4")
    
    # Check for insufficient inputs
    if s3 is None or s4 is None or s3.fired is None or s4.fired is None:
        missing = []
        if s3 is None or s3.fired is None:
            missing.append("S3")
        if s4 is None or s4.fired is None:
            missing.append("S4")
        return GateResult(
            id="G2",
            fired=False,
            status="insufficient_inputs",
            rationale=f"Missing required inputs: {', '.join(missing)}"
        )
    
    fired = s3.fired and s4.fired
    
    if not fired:
        return GateResult(
            id="G2",
            fired=False,
            rationale="Analysis-Gaming requires both S3 (subgroup-only win) and S4 (ITT/PP dropout asymmetry)"
        )
    
    # Build rationale with evidence
    rationale_parts = ["Analysis-Gaming: Both S3 (subgroup-only win) and S4 (ITT/PP dropout asymmetry) fired"]
    supporting_signals = ["S3", "S4"]
    
    if s3.value is not None:
        rationale_parts.append(f"S3 value: {s3.value}")
    if s4.value is not None:
        rationale_parts.append(f"S4 value: {s4.value}")
    
    return GateResult(
        id="G2",
        fired=True,
        supporting_signals=supporting_signals,
        rationale="; ".join(rationale_parts)
    )


def G3_plausibility(signals: Dict[str, SignalResult]) -> GateResult:
    """
    G3: Plausibility = S5 & (S7 | S6)
    
    Requires implausible effect size (S5) AND (single-arm where RCT standard OR multiple interims w/o alpha spending).
    """
    s5 = signals.get("S5")
    s6 = signals.get("S6")
    s7 = signals.get("S7")
    
    # Check for insufficient inputs
    if s5 is None or s5.fired is None:
        return GateResult(
            id="G3",
            fired=False,
            status="insufficient_inputs",
            rationale="Missing required input: S5"
        )
    
    # S6 and S7 can be None (not required)
    s6_fired = s6.fired if s6 is not None and s6.fired is not None else False
    s7_fired = s7.fired if s7 is not None and s7.fired is not None else False
    
    fired = s5.fired and (s6_fired or s7_fired)
    
    if not fired:
        return GateResult(
            id="G3",
            fired=False,
            rationale="Plausibility requires S5 (implausible effect) AND (S6 OR S7)"
        )
    
    # Build rationale with evidence
    rationale_parts = ["Plausibility: S5 (implausible effect) fired"]
    supporting_signals = ["S5"]
    
    if s6_fired:
        rationale_parts.append("S6 (multiple interims w/o alpha spending) fired")
        supporting_signals.append("S6")
    if s7_fired:
        rationale_parts.append("S7 (single-arm where RCT standard) fired")
        supporting_signals.append("S7")
    
    if s5.value is not None:
        rationale_parts.append(f"S5 value: {s5.value}")
    
    return GateResult(
        id="G3",
        fired=True,
        supporting_signals=supporting_signals,
        rationale="; ".join(rationale_parts)
    )


def G4_p_hacking(signals: Dict[str, SignalResult]) -> GateResult:
    """
    G4: p-Hacking = S8 & (S1 | S3)
    
    Requires p-value cusp (S8) AND (endpoint change OR subgroup-only win).
    """
    s1 = signals.get("S1")
    s3 = signals.get("S3")
    s8 = signals.get("S8")
    
    # Check for insufficient inputs
    if s8 is None or s8.fired is None:
        return GateResult(
            id="G4",
            fired=False,
            status="insufficient_inputs",
            rationale="Missing required input: S8"
        )
    
    # S1 and S3 can be None (not required)
    s1_fired = s1.fired if s1 is not None and s1.fired is not None else False
    s3_fired = s3.fired if s3 is not None and s3.fired is not None else False
    
    fired = s8.fired and (s1_fired or s3_fired)
    
    if not fired:
        return GateResult(
            id="G4",
            fired=False,
            rationale="p-Hacking requires S8 (p-value cusp) AND (S1 OR S3)"
        )
    
    # Build rationale with evidence
    rationale_parts = ["p-Hacking: S8 (p-value cusp) fired"]
    supporting_signals = ["S8"]
    
    if s1_fired:
        rationale_parts.append("S1 (endpoint change) fired")
        supporting_signals.append("S1")
    if s3_fired:
        rationale_parts.append("S3 (subgroup-only win) fired")
        supporting_signals.append("S3")
    
    if s8.value is not None:
        rationale_parts.append(f"S8 value: {s8.value}")
    
    return GateResult(
        id="G4",
        fired=True,
        supporting_signals=supporting_signals,
        rationale="; ".join(rationale_parts)
    )


def evaluate_all_gates(signals: Dict[str, SignalResult]) -> Dict[str, GateResult]:
    """
    Evaluate all gates G1-G4.
    
    Args:
        signals: Dictionary of signal results keyed by signal ID
        
    Returns:
        Dictionary of gate results keyed by gate ID
    """
    gates = {
        "G1": G1_alpha_meltdown(signals),
        "G2": G2_analysis_gaming(signals),
        "G3": G3_plausibility(signals),
        "G4": G4_p_hacking(signals)
    }
    
    return gates


def evaluate_stop_rules(
    study_cards: List[Dict],
    trial_versions: List[Dict],
    config: Dict
) -> Optional[str]:
    """
    Evaluate stop rules that override scoring.
    
    Args:
        study_cards: List of study card dictionaries
        trial_versions: List of trial version dictionaries
        config: Configuration with stop rule settings
        
    Returns:
        Stop rule name if triggered, None otherwise
    """
    stop_rules = config.get("stop_rules", {})
    
    # Check endpoint switch after LPR
    if stop_rules.get("endpoint_switched_after_LPR", False):
        # TODO: Implement endpoint switch detection from trial_versions
        pass
    
    # Check PP-only success with high missing ITT
    if stop_rules.get("pp_only_success_with_missing_itt_gt20", False):
        # TODO: Implement ITT/PP missingness analysis from study_cards
        pass
    
    # Check unblinded subjective primary where blinding feasible
    if stop_rules.get("unblinded_subjective_primary_feasible_blinding", False):
        # TODO: Implement blinding feasibility analysis
        pass
    
    return None


def get_fired_gates(gates: Dict[str, GateResult]) -> List[str]:
    """Get list of fired gate IDs."""
    return [gate_id for gate_id, gate in gates.items() if gate.fired]


def calculate_total_likelihood_ratio(gates: Dict[str, GateResult], lr_table: Dict[str, float]) -> float:
    """
    Calculate total likelihood ratio from fired gates.
    
    Args:
        gates: Dictionary of gate results
        lr_table: Dictionary mapping gate IDs to likelihood ratios
        
    Returns:
        Total likelihood ratio (product of individual LRs)
    """
    total_lr = 1.0
    
    for gate_id, gate in gates.items():
        if gate.fired:
            lr = lr_table.get(gate_id, 1.0)
            total_lr *= lr
    
    return total_lr
