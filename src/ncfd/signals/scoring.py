"""
Scoring System for Signal Evaluation

Implements posterior probability calculation based on fired gates and likelihood ratios.
"""

import logging
import math
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    """Result of trial scoring."""
    trial_id: str
    run_id: str
    prior_pi: float
    logit_prior: float
    sum_log_lr: float
    logit_post: float
    p_fail: float
    stop_rule_applied: Optional[str] = None


def score_trial(trial_id: str, run_id: str, gates: Dict[str, Any], 
                prior_pi: Optional[float] = None) -> ScoreResult:
    """
    Calculate posterior probability for a trial based on fired gates.
    
    Args:
        trial_id: Trial identifier
        run_id: Run identifier
        gates: Dictionary of gate results {gate_id: GateResult}
        prior_pi: Prior failure probability (defaults to system default)
    
    Returns:
        ScoreResult with posterior probability
    """
    if prior_pi is None:
        prior_pi = get_default_prior_pi()
    
    # Calculate logit of prior
    logit_prior = math.log(prior_pi / (1 - prior_pi))
    
    # Sum log likelihood ratios from fired gates
    sum_log_lr = 0.0
    fired_gates = []
    
    for gate_id, gate_result in gates.items():
        if gate_result.fired:
            fired_gates.append(gate_id)
            sum_log_lr += math.log(gate_result.lr_used)
    
    # Calculate posterior logit
    logit_post = logit_prior + sum_log_lr
    
    # Convert back to probability
    p_fail = 1 / (1 + math.exp(-logit_post))
    
    # Apply stop rules if applicable
    stop_rule_applied = _apply_stop_rules(gates, p_fail)
    if stop_rule_applied:
        p_fail = 0.97  # Set to high failure probability
    
    return ScoreResult(
        trial_id=trial_id,
        run_id=run_id,
        prior_pi=prior_pi,
        logit_prior=logit_prior,
        sum_log_lr=sum_log_lr,
        logit_post=logit_post,
        p_fail=p_fail,
        stop_rule_applied=stop_rule_applied
    )


def get_default_prior_pi() -> float:
    """Get default prior failure probability."""
    return 0.55  # From config: prior_failure_rate: 0.55


def _apply_stop_rules(gates: Dict[str, Any], p_fail: float) -> Optional[str]:
    """
    Apply stop rules that override the calculated probability.
    
    Args:
        gates: Dictionary of gate results
        p_fail: Calculated failure probability
    
    Returns:
        Stop rule name if applied, None otherwise
    """
    # Stop rule: endpoint switched after LPR
    if "G1" in gates and gates["G1"].fired:
        # Check if this represents endpoint switching after LPR
        if "S1" in gates["G1"].supporting_signals:
            return "endpoint_switched_after_LPR"
    
    # Stop rule: PP-only success with ITT missing >20%
    if "G2" in gates and gates["G2"].fired:
        # Check if this represents PP-only success with high dropout
        if "S4" in gates["G2"].supporting_signals:
            return "pp_only_success_with_itt_missing_gt"
    
    # Stop rule: unblinded subjective primary where blinding feasible
    if "G3" in gates and gates["G3"].fired:
        # Check if this represents unblinded subjective primary
        if "S7" in gates["G3"].supporting_signals:
            return "unblinded_subjective_primary_when_blinding_feasible"
    
    return None
