"""
G1-G4 Gate Evaluation System

Implementation of the G1-G4 gate evaluation system based on fired signals.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """Result of gate evaluation."""
    gate_id: str
    fired: bool
    supporting_signals: List[str]
    supporting_evidence: List[str]
    lr_used: float
    rationale: str


def evaluate_all_gates(signals: Dict[str, Any], gate_config: Optional[Dict[str, Any]] = None) -> Dict[str, GateResult]:
    """
    Evaluate all gates based on fired signals.
    
    Args:
        signals: Dictionary of signal results {signal_id: SignalResult}
        gate_config: Gate configuration (optional)
    
    Returns:
        Dictionary of gate results {gate_id: GateResult}
    """
    print(f"🚪 GATES: Evaluating gates with signals: {[(k, v.fired, v.reason) for k, v in signals.items()]}")
    if gate_config is None:
        gate_config = _get_default_gate_config()
    
    # Get fired signals
    fired_signals = {sid: result for sid, result in signals.items() if result.fired}
    
    gate_results = {}
    
    # G1: Alpha-Meltdown = S1 & S2
    if "G1" in gate_config:
        gate_results["G1"] = _evaluate_g1(fired_signals)
    
    # G2: Analysis-Gaming = S3 & S4
    if "G2" in gate_config:
        gate_results["G2"] = _evaluate_g2(fired_signals)
    
    # G3: Plausibility = S5 & (S7 | S6)
    if "G3" in gate_config:
        gate_results["G3"] = _evaluate_g3(fired_signals)
    
    # G4: p-Hacking = S8 & (S1 | S3)
    if "G4" in gate_config:
        gate_results["G4"] = _evaluate_g4(fired_signals)
    
    return gate_results


def _evaluate_g1(fired_signals: Dict[str, Any]) -> GateResult:
    """G1: Alpha-Meltdown = S1 & S2"""
    s1_fired = "S1" in fired_signals
    s2_fired = "S2" in fired_signals
    
    fired = s1_fired and s2_fired
    supporting_signals = []
    supporting_evidence = []
    
    if fired:
        supporting_signals = ["S1", "S2"]
        if s1_fired:
            supporting_evidence.extend(fired_signals["S1"].evidence_ids or [])
        if s2_fired:
            supporting_evidence.extend(fired_signals["S2"].evidence_ids or [])
        rationale = "S1 & S2 present - Alpha meltdown detected"
        lr_used = 5.0  # From config
    else:
        missing = []
        if not s1_fired:
            missing.append("S1")
        if not s2_fired:
            missing.append("S2")
        rationale = f"Missing {', '.join(missing)} - No alpha meltdown"
        lr_used = 1.0
    
    return GateResult(
        gate_id="G1",
        fired=fired,
        supporting_signals=supporting_signals,
        supporting_evidence=supporting_evidence,
        lr_used=lr_used,
        rationale=rationale
    )


def _evaluate_g2(fired_signals: Dict[str, Any]) -> GateResult:
    """G2: Analysis-Gaming = S3 & S4"""
    s3_fired = "S3" in fired_signals
    s4_fired = "S4" in fired_signals
    
    fired = s3_fired and s4_fired
    supporting_signals = []
    supporting_evidence = []
    
    if fired:
        supporting_signals = ["S3", "S4"]
        if s3_fired:
            supporting_evidence.extend(fired_signals["S3"].evidence_ids or [])
        if s4_fired:
            supporting_evidence.extend(fired_signals["S4"].evidence_ids or [])
        rationale = "S3 & S4 present - Analysis gaming detected"
        lr_used = 6.0  # From config
    else:
        missing = []
        if not s3_fired:
            missing.append("S3")
        if not s4_fired:
            missing.append("S4")
        rationale = f"Missing {', '.join(missing)} - No analysis gaming"
        lr_used = 1.0
    
    return GateResult(
        gate_id="G2",
        fired=fired,
        supporting_signals=supporting_signals,
        supporting_evidence=supporting_evidence,
        lr_used=lr_used,
        rationale=rationale
    )


def _evaluate_g3(fired_signals: Dict[str, Any]) -> GateResult:
    """G3: Plausibility = S5 & (S7 | S6)"""
    s5_fired = "S5" in fired_signals
    s6_fired = "S6" in fired_signals
    s7_fired = "S7" in fired_signals
    
    fired = s5_fired and (s6_fired or s7_fired)
    supporting_signals = []
    supporting_evidence = []
    
    if fired:
        supporting_signals = ["S5"]
        if s6_fired:
            supporting_signals.append("S6")
        if s7_fired:
            supporting_signals.append("S7")
        
        if s5_fired:
            supporting_evidence.extend(fired_signals["S5"].evidence_ids or [])
        if s6_fired:
            supporting_evidence.extend(fired_signals["S6"].evidence_ids or [])
        if s7_fired:
            supporting_evidence.extend(fired_signals["S7"].evidence_ids or [])
        
        rationale = "S5 & (S7 | S6) present - Plausibility concerns"
        lr_used = 4.0  # From config
    else:
        missing = []
        if not s5_fired:
            missing.append("S5")
        if not s6_fired and not s7_fired:
            missing.append("(S7 | S6)")
        rationale = f"Missing {', '.join(missing)} - No plausibility concerns"
        lr_used = 1.0
    
    return GateResult(
        gate_id="G3",
        fired=fired,
        supporting_signals=supporting_signals,
        supporting_evidence=supporting_evidence,
        lr_used=lr_used,
        rationale=rationale
    )


def _evaluate_g4(fired_signals: Dict[str, Any]) -> GateResult:
    """G4: p-Hacking = S8 & (S1 | S3)"""
    s8_fired = "S8" in fired_signals
    s1_fired = "S1" in fired_signals
    s3_fired = "S3" in fired_signals
    
    fired = s8_fired and (s1_fired or s3_fired)
    supporting_signals = []
    supporting_evidence = []
    
    if fired:
        supporting_signals = ["S8"]
        if s1_fired:
            supporting_signals.append("S1")
        if s3_fired:
            supporting_signals.append("S3")
        
        if s8_fired:
            supporting_evidence.extend(fired_signals["S8"].evidence_ids or [])
        if s1_fired:
            supporting_evidence.extend(fired_signals["S1"].evidence_ids or [])
        if s3_fired:
            supporting_evidence.extend(fired_signals["S3"].evidence_ids or [])
        
        rationale = "S8 & (S1 | S3) present - p-Hacking detected"
        lr_used = 3.5  # From config
    else:
        missing = []
        if not s8_fired:
            missing.append("S8")
        if not s1_fired and not s3_fired:
            missing.append("(S1 | S3)")
        rationale = f"Missing {', '.join(missing)} - No p-hacking"
        lr_used = 1.0
    
    return GateResult(
        gate_id="G4",
        fired=fired,
        supporting_signals=supporting_signals,
        supporting_evidence=supporting_evidence,
        lr_used=lr_used,
        rationale=rationale
    )


def _get_default_gate_config() -> Dict[str, Any]:
    """Get default gate configuration."""
    return {
        "G1": {"requires": ["S1", "S2"]},
        "G2": {"requires": ["S3", "S4"]},
        "G3": {"requires_any": ["S6", "S7"], "also_requires": ["S5"]},
        "G4": {"requires": ["S8"], "requires_any": ["S1", "S3"]}
    }
