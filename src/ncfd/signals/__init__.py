"""
Signals module for precision-first "near-certain failure" detection.

Implements S1-S9 primitives, gates G1-G4, and scoring for biotech pivotal trials.
"""

from .types import SignalResult, GateResult, ScoreResult, GateConfig
from .primitives import (
    S1_endpoint_changed,
    S2_underpowered_pivotal,
    S3_subgroup_only_no_multiplicity,
    S4_itt_vs_pp_dropout,
    S5_implausible_vs_graveyard,
    S6_many_interims_no_spending,
    S7_single_arm_where_rct_standard,
    S7b_randomized_withdrawal_after_OLE,
    S8_pvalue_cusp_or_heaping,
    S9_os_pfs_contradiction
)
from .gates import (
    G1_alpha_meltdown,
    G2_analysis_gaming,
    G3_plausibility,
    G4_p_hacking,
    evaluate_all_gates,
    get_fired_gates,
    calculate_total_likelihood_ratio
)
from .scoring import (
    score_trial,
    compute_p_fail,
    load_gate_lr_config,
    logit,
    inv_logit,
    get_default_prior_pi,
    interpret_score,
    format_score_summary
)
from .study_card_mapper import build_study_card

__all__ = [
    # Types
    'SignalResult',
    'GateResult', 
    'ScoreResult',
    'GateConfig',
    
    # Signal primitives
    'S1_endpoint_changed',
    'S2_underpowered_pivotal',
    'S3_subgroup_only_no_multiplicity',
    'S4_itt_vs_pp_dropout',
    'S5_implausible_vs_graveyard',
    'S6_many_interims_no_spending',
    'S7_single_arm_where_rct_standard',
    'S7b_randomized_withdrawal_after_OLE',
    'S8_pvalue_cusp_or_heaping',
    'S9_os_pfs_contradiction',
    
    # Gates
    'G1_alpha_meltdown',
    'G2_analysis_gaming',
    'G3_plausibility',
    'G4_p_hacking',
    'evaluate_all_gates',
    'get_fired_gates',
    'calculate_total_likelihood_ratio',
    
    # Scoring
    'score_trial',
    'compute_p_fail',
    'load_gate_lr_config',
    'logit',
    'inv_logit',
    'get_default_prior_pi',
    'interpret_score',
    'format_score_summary',
    
    # Utilities
    'build_study_card'
]
