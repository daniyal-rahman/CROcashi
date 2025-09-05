"""
Bayesian scoring system for precision-first failure detection.

Implements the scoring algorithm from global_prompt.md:
Posterior via log-odds using calibrated likelihood ratios (LRs) mainly for gates (dominant), 
small/zero for primitives. Stop rules override to P_fail≈0.97.
"""

import math
import yaml
from typing import Dict, Optional, List
from datetime import datetime
from .types import ScoreResult, GateResult, SignalResult, GateConfig
from .gates import evaluate_stop_rules


def logit(p: float) -> float:
    """Convert probability to logit scale."""
    if p <= 0:
        return float('-inf')
    elif p >= 1:
        return float('inf')
    else:
        return math.log(p / (1 - p))


def inv_logit(z: float) -> float:
    """Convert logit to probability."""
    if z == float('-inf'):
        return 0.0
    elif z == float('inf'):
        return 1.0
    else:
        return 1 / (1 + math.exp(-z))


def load_gate_lr_config(config_path: str = "config/gate_lrs.yaml") -> GateConfig:
    """
    Load gate likelihood ratio configuration.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        GateConfig object with validated settings
    """
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Extract gate LRs
        gates = {}
        for gate_id, gate_data in config_data.get("gates", {}).items():
            if isinstance(gate_data, dict):
                gates[gate_id] = gate_data.get("lr", 1.0)
            else:
                gates[gate_id] = float(gate_data)
        
        # Extract primitive LRs (default to 1.0)
        primitive_lrs = config_data.get("primitives", {}).get("overrides", {})
        
        # Extract caps and bounds
        global_config = config_data.get("global", {})
        lr_caps = {
            "min": global_config.get("lr_min", 1.0),
            "max": global_config.get("lr_max", 10.0)
        }
        p_cap = {
            "min": global_config.get("prior_floor", 0.01),
            "max": global_config.get("prior_ceil", 0.99)
        }
        
        # Extract stop rules
        stop_rules = {}
        for rule_name, rule_data in config_data.get("stop_rules", {}).items():
            if isinstance(rule_data, dict):
                stop_rules[rule_name] = rule_data.get("enabled", True)
            else:
                stop_rules[rule_name] = bool(rule_data)
        
        # Convert version to string
        version = config_data.get("version", "unknown")
        if hasattr(version, 'isoformat'):
            version = version.isoformat()
        
        return GateConfig(
            version=str(version),
            gates=gates,
            primitive_lrs=primitive_lrs,
            lr_caps=lr_caps,
            stop_rules=stop_rules,
            p_cap=p_cap
        )
        
    except Exception as e:
        raise ValueError(f"Failed to load gate LR config from {config_path}: {e}")


def compute_p_fail(
    prior_pi: float,
    gates: Dict[str, GateResult],
    lr_table: Dict[str, float],
    primitive_lrs: Optional[Dict[str, float]] = None,
    stop_rule: Optional[str] = None,
    cap: tuple = (0.01, 0.99)
) -> ScoreResult:
    """
    Compute posterior failure probability using log-odds with likelihood ratios.
    
    Args:
        prior_pi: Prior probability of failure
        gates: Dictionary of gate results
        lr_table: Dictionary mapping gate IDs to likelihood ratios
        primitive_lrs: Optional dictionary mapping signal IDs to LRs (default 1.0)
        stop_rule: Optional stop rule name that overrides calculation
        cap: Tuple of (min, max) probability bounds
        
    Returns:
        ScoreResult with full traceability
    """
    # Handle stop rule override
    if stop_rule is not None:
        p_fail = cap[1]  # Use max cap (typically 0.99)
        return ScoreResult(
            trial_id="",  # Will be set by caller
            run_id="",    # Will be set by caller
            prior_pi=prior_pi,
            logit_prior=logit(prior_pi),
            p_fail=p_fail,
            logit_post=logit(p_fail),
            sum_log_lr=0.0,
            stop_rule_applied=stop_rule,
            config_version=""
        )
    
    # Start with logit prior
    z = logit(prior_pi)
    
    # Add log LRs for fired gates
    sum_log_lr = 0.0
    fired_gates = []
    
    for gate_id, gate in gates.items():
        if gate.fired:
            lr = lr_table.get(gate_id, 1.0)
            # Apply LR caps from config
            lr = max(0.1, min(100.0, lr))  # Allow higher LRs for extreme cases
            sum_log_lr += math.log(lr)
            fired_gates.append(gate_id)
    
    # Add small contribution from primitives (optional)
    if primitive_lrs:
        for signal_id, lr in primitive_lrs.items():
            # TODO: Get signal result and check if fired
            # For now, skip primitive contribution
            pass
    
    # Compute posterior
    z += sum_log_lr
    p_fail = inv_logit(z)
    
    # Apply probability caps
    p_fail = max(cap[0], min(cap[1], p_fail))
    
    return ScoreResult(
        trial_id="",  # Will be set by caller
        run_id="",    # Will be set by caller
        prior_pi=prior_pi,
        logit_prior=logit(prior_pi),
        fired_gates=fired_gates,
        sum_log_lr=sum_log_lr,
        logit_post=logit(p_fail),
        p_fail=p_fail,
        config_version=""
    )


def score_trial(
    trial_id: str,
    run_id: str,
    prior_pi: float,
    signals: Dict[str, SignalResult],
    gates: Dict[str, GateResult],
    config: GateConfig,
    stop_rule: Optional[str] = None
) -> ScoreResult:
    """
    Score a trial using the Bayesian system with full traceability.
    
    Args:
        trial_id: Trial identifier
        run_id: Run identifier for audit trail
        prior_pi: Prior probability of failure
        signals: Dictionary of signal results
        gates: Dictionary of gate results
        config: Gate configuration with LRs and caps
        stop_rule: Optional stop rule that overrides calculation
        
    Returns:
        ScoreResult with full traceability
    """
    # Compute posterior
    result = compute_p_fail(
        prior_pi=prior_pi,
        gates=gates,
        lr_table=config.gates,
        primitive_lrs=config.primitive_lrs,
        stop_rule=stop_rule,
        cap=(config.p_cap["min"], config.p_cap["max"])
    )
    
    # Fill in missing fields
    result.trial_id = trial_id
    result.run_id = run_id
    result.config_version = config.version
    
    return result


# Removed duplicate evaluate_stop_rules - use the one from gates.py instead


def get_default_prior_pi() -> float:
    """Get default prior probability of failure for pivotal trials."""
    return 0.65  # From historical pivotal failure rate


def interpret_score(score: ScoreResult) -> str:
    """
    Interpret a score result for human consumption.
    
    Args:
        score: ScoreResult to interpret
        
    Returns:
        Human-readable interpretation
    """
    if score.stop_rule_applied:
        return f"Stop rule '{score.stop_rule_applied}' applied: P_fail = {score.p_fail:.3f}"
    
    if score.p_fail >= 0.9:
        level = "CRITICAL"
    elif score.p_fail >= 0.7:
        level = "HIGH"
    elif score.p_fail >= 0.5:
        level = "MEDIUM"
    else:
        level = "LOW"
    
    fired_count = len(score.fired_gates)
    if fired_count == 0:
        gate_summary = "No gates fired"
    elif fired_count == 1:
        gate_summary = f"Gate {score.fired_gates[0]} fired"
    else:
        gate_summary = f"Gates {', '.join(score.fired_gates)} fired"
    
    return f"{level} RISK: P_fail = {score.p_fail:.3f} (prior: {score.prior_pi:.3f}). {gate_summary}"


def format_score_summary(scores: List[ScoreResult]) -> str:
    """
    Format a summary of multiple scores.
    
    Args:
        scores: List of ScoreResult objects
        
    Returns:
        Formatted summary string
    """
    if not scores:
        return "No scores to summarize"
    
    # Count by risk level
    critical = sum(1 for s in scores if s.p_fail >= 0.9)
    high = sum(1 for s in scores if 0.7 <= s.p_fail < 0.9)
    medium = sum(1 for s in scores if 0.5 <= s.p_fail < 0.7)
    low = sum(1 for s in scores if s.p_fail < 0.5)
    
    # Count fired gates
    gate_counts = {}
    for score in scores:
        for gate in score.fired_gates:
            gate_counts[gate] = gate_counts.get(gate, 0) + 1
    
    summary = f"Score Summary ({len(scores)} trials):\n"
    summary += f"  Critical (P≥0.9): {critical}\n"
    summary += f"  High (0.7≤P<0.9): {high}\n"
    summary += f"  Medium (0.5≤P<0.7): {medium}\n"
    summary += f"  Low (P<0.5): {low}\n"
    
    if gate_counts:
        summary += "  Most fired gates:\n"
        for gate, count in sorted(gate_counts.items(), key=lambda x: x[1], reverse=True)[:3]:
            summary += f"    {gate}: {count} trials\n"
    
    return summary
