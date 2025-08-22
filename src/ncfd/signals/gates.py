"""
Gate logic for trial failure detection.

This module implements the 4 gates (G1-G4) that combine multiple signals
to create higher-level failure detection patterns. Gates are co-dependent
and use calibrated likelihood ratios for scoring.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Iterable, Optional, Set, Any
import yaml
import os
from pathlib import Path


@dataclass
class SignalEvidence:
    """Evidence for a signal with source tracking."""
    S_id: str
    evidence_span: dict  # {source_study_id, quote?, page?, start?, end?}
    severity: Optional[str] = None  # 'low'|'medium'|'high' (optional)


@dataclass
class GateEval:
    """Result of a gate evaluation with comprehensive metadata."""
    gate_id: str
    fired: bool
    supporting_S: List[str]
    supporting_evidence: List[SignalEvidence]
    lr_used: float
    rationale: str


@dataclass
class GateResult:
    """Legacy compatibility class - will be deprecated."""
    fired: bool
    G_id: str  # G1, G2, G3, G4
    supporting_S_ids: List[str]  # List of S_ids that support this gate
    lr_used: Optional[float] = None  # Likelihood ratio for this gate
    rationale_text: str = ""
    severity: str = "M"  # Aggregated severity from supporting signals
    metadata: Optional[Dict[str, Any]] = None


def _has(signals: Set[str], *needed: str) -> bool:
    """Check if all required signals are present."""
    return all(s in signals for s in needed)


def _has_any(signals: Set[str], *candidates: str) -> bool:
    """Check if any of the candidate signals are present."""
    return any(s in signals for s in candidates)


def load_gate_config(config_path: Optional[str] = None) -> dict:
    """Load gate configuration from YAML file."""
    if config_path is None:
        # Default to config directory relative to this file
        current_dir = Path(__file__).parent.parent.parent.parent
        config_path = current_dir / "config" / "gate_lrs.yaml"
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Gate configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def evaluate_gates(
    present_signals: Set[str],
    evidence_by_signal: Dict[str, List[SignalEvidence]],
    cfg: Optional[dict] = None,
) -> Dict[str, GateEval]:
    """
    Evaluate all gates based on present signals and evidence.
    
    Args:
        present_signals: Set of signal IDs that are present (e.g., {'S1','S2','S5','S7','S8'})
        evidence_by_signal: Map S_id -> [SignalEvidence,...]
        cfg: Parsed YAML dict for gate LRs (loaded automatically if None)
    
    Returns:
        Dictionary mapping gate_id -> GateEval
    """
    if cfg is None:
        cfg = load_gate_config()
    
    gcfg = cfg["gates"]
    out: Dict[str, GateEval] = {}

    def choose_lr(gid: str, supports: List[SignalEvidence]) -> float:
        """Choose likelihood ratio based on severity and configuration."""
        base = gcfg[gid].get("lr", 1.0)
        by_sev = gcfg[gid].get("by_severity", {})
        
        # If multiple severities, take max to stay precision-first (conservative)
        if by_sev and supports:
            severities = [e.severity for e in supports if e.severity in by_sev]
            if severities:
                base = max(by_sev[s] for s in severities)
        return float(base)

    # ---- Gate definitions ----
    # G1: Alpha-Meltdown = S1 & S2
    if "G1" in gcfg:
        fired = _has(present_signals, "S1", "S2")
        supports = []
        for sid in ("S1", "S2"):
            supports.extend(evidence_by_signal.get(sid, []))
        out["G1"] = GateEval(
            gate_id="G1",
            fired=fired,
            supporting_S=["S1", "S2"] if fired else [],
            supporting_evidence=supports if fired else [],
            lr_used=choose_lr("G1", supports) if fired else 1.0,
            rationale="S1 & S2 present" if fired else "Missing S1 or S2",
        )

    # G2: Analysis-Gaming = S3 & S4
    if "G2" in gcfg:
        fired = _has(present_signals, "S3", "S4")
        supports = []
        for sid in ("S3", "S4"):
            supports.extend(evidence_by_signal.get(sid, []))
        out["G2"] = GateEval(
            gate_id="G2",
            fired=fired,
            supporting_S=["S3", "S4"] if fired else [],
            supporting_evidence=supports if fired else [],
            lr_used=choose_lr("G2", supports) if fired else 1.0,
            rationale="S3 & S4 present" if fired else "Missing S3 or S4",
        )

    # G3: Plausibility = S5 & (S7 | S6)
    if "G3" in gcfg:
        fired = "S5" in present_signals and _has_any(present_signals, "S7", "S6")
        supports = []
        for sid in ("S5", "S7", "S6"):
            supports.extend(evidence_by_signal.get(sid, []))
        out["G3"] = GateEval(
            gate_id="G3",
            fired=fired,
            supporting_S=["S5"] + [s for s in ("S7", "S6") if s in present_signals] if fired else [],
            supporting_evidence=supports if fired else [],
            lr_used=choose_lr("G3", supports) if fired else 1.0,
            rationale="S5 & (S7 | S6) present" if fired else "Missing S5 and/or (S7|S6)",
        )

    # G4: p-Hacking = S8 & (S1 | S3)
    if "G4" in gcfg:
        fired = "S8" in present_signals and _has_any(present_signals, "S1", "S3")
        supports = []
        for sid in ("S8", "S1", "S3"):
            supports.extend(evidence_by_signal.get(sid, []))
        out["G4"] = GateEval(
            gate_id="G4",
            fired=fired,
            supporting_S=["S8"] + [s for s in ("S1", "S3") if s in present_signals] if fired else [],
            supporting_evidence=supports if fired else [],
            lr_used=choose_lr("G4", supports) if fired else 1.0,
            rationale="S8 & (S1 | S3) present" if fired else "Missing S8 and/or (S1|S3)",
        )

    return out


# ---- Legacy compatibility functions ----

def G1_alpha_meltdown(signals: Dict[str, 'SignalResult']) -> GateResult:
    """
    G1: Alpha-Meltdown = S1 & S2 (Legacy compatibility)
    
    Detects when a trial changes its endpoint late AND is underpowered,
    indicating potential alpha inflation and statistical gaming.
    """
    # Convert to new format for evaluation
    present_signals = {k for k, v in signals.items() if v and v.fired}
    evidence_by_signal = {k: [] for k in present_signals}  # Empty evidence for legacy
    
    gate_evals = evaluate_gates(present_signals, evidence_by_signal)
    g1_eval = gate_evals.get("G1")
    
    if g1_eval and g1_eval.fired:
        return GateResult(
            fired=True,
            G_id="G1",
            supporting_S_ids=g1_eval.supporting_S,
            lr_used=g1_eval.lr_used,
            rationale_text=g1_eval.rationale,
            severity="H" if g1_eval.lr_used > 5.0 else "M"
        )
    
    return GateResult(
        fired=False,
        G_id="G1",
        supporting_S_ids=[],
        rationale_text="S1 and S2 not both fired"
    )


def G2_analysis_gaming(signals: Dict[str, 'SignalResult']) -> GateResult:
    """
    G2: Analysis-Gaming = S3 & S4 (Legacy compatibility)
    
    Detects when a trial shows subgroup-only wins without multiplicity control
    AND has ITT/PP contradictions with dropout asymmetry.
    """
    present_signals = {k for k, v in signals.items() if v and v.fired}
    evidence_by_signal = {k: [] for k in present_signals}
    
    gate_evals = evaluate_gates(present_signals, evidence_by_signal)
    g2_eval = gate_evals.get("G2")
    
    if g2_eval and g2_eval.fired:
        return GateResult(
            fired=True,
            G_id="G2",
            supporting_S_ids=g2_eval.supporting_S,
            lr_used=g2_eval.lr_used,
            rationale_text=g2_eval.rationale,
            severity="H" if g2_eval.lr_used > 5.0 else "M"
        )
    
    return GateResult(
        fired=False,
        G_id="G2",
        supporting_S_ids=[],
        rationale_text="S3 and S4 not both fired"
    )


def G3_plausibility(signals: Dict[str, 'SignalResult']) -> GateResult:
    """
    G3: Plausibility = S5 & (S7 | S6) (Legacy compatibility)
    
    Detects when a trial has implausible effect sizes AND either multiple
    interim looks or single-arm design where RCT is standard.
    """
    present_signals = {k for k, v in signals.items() if v and v.fired}
    evidence_by_signal = {k: [] for k in present_signals}
    
    gate_evals = evaluate_gates(present_signals, evidence_by_signal)
    g3_eval = gate_evals.get("G3")
    
    if g3_eval and g3_eval.fired:
        return GateResult(
            fired=True,
            G_id="G3",
            supporting_S_ids=g3_eval.supporting_S,
            lr_used=g3_eval.lr_used,
            rationale_text=g3_eval.rationale,
            severity="H" if g3_eval.lr_used > 5.0 else "M"
        )
    
    return GateResult(
        fired=False,
        G_id="G3",
        supporting_S_ids=[],
        rationale_text="S5 and (S7 or S6) not both present"
    )


def G4_p_hacking(signals: Dict[str, 'SignalResult']) -> GateResult:
    """
    G4: p-Hacking = S8 & (S1 | S3) (Legacy compatibility)
    
    Detects when a trial has p-value cusp AND either endpoint changes
    or subgroup-only wins without multiplicity control.
    """
    present_signals = {k for k, v in signals.items() if v and v.fired}
    evidence_by_signal = {k: [] for k in present_signals}
    
    gate_evals = evaluate_gates(present_signals, evidence_by_signal)
    g4_eval = gate_evals.get("G4")
    
    if g4_eval and g4_eval.fired:
        return GateResult(
            fired=True,
            G_id="G4",
            supporting_S_ids=g4_eval.supporting_S,
            lr_used=g4_eval.lr_used,
            rationale_text=g4_eval.rationale,
            severity="H" if g4_eval.lr_used > 5.0 else "M"
        )
    
    return GateResult(
        fired=False,
        G_id="G4",
        supporting_S_ids=[],
        rationale_text="S8 and (S1 or S3) not both present"
    )


def get_fired_gates(signals: Dict[str, 'SignalResult']) -> List[GateResult]:
    """Get all fired gates (legacy compatibility)."""
    present_signals = {k for k, v in signals.items() if v and v.fired}
    evidence_by_signal = {k: [] for k in present_signals}
    
    gate_evals = evaluate_gates(present_signals, evidence_by_signal)
    
    results = []
    for gate_id, eval_result in gate_evals.items():
        if eval_result.fired:
            results.append(GateResult(
                fired=True,
                G_id=gate_id,
                supporting_S_ids=eval_result.supporting_S,
                lr_used=eval_result.lr_used,
                rationale_text=eval_result.rationale,
                severity="H" if eval_result.lr_used > 5.0 else "M"
            ))
    
    return results


def calculate_total_likelihood_ratio(gates: List[GateResult]) -> float:
    """Calculate total likelihood ratio from fired gates (legacy compatibility)."""
    total_lr = 1.0
    for gate in gates:
        if gate.fired and gate.lr_used:
            total_lr *= gate.lr_used
    return total_lr
