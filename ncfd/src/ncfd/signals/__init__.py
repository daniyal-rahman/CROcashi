"""
Signals module for trial failure detection.

This module provides signal primitives (S1-S9) and gates (G1-G4)
for detecting various red flags in clinical trial data.
"""

from .primitives import (
    SignalResult,
    S1_endpoint_changed,
    S2_underpowered_pivotal,
    S3_subgroup_only_no_multiplicity,
    S4_itt_vs_pp_dropout,
    S5_implausible_vs_graveyard,
    S6_many_interims_no_spending,
    S7_single_arm_where_rct_standard,
    S8_pvalue_cusp_or_heaping,
    S9_os_pfs_contradiction,
    evaluate_all_signals,
    get_fired_signals,
    get_high_severity_signals,
)

from .gates import (
    # New enhanced gate evaluation system
    SignalEvidence,
    GateEval,
    evaluate_gates,
    load_gate_config,
    
    # Legacy compatibility
    GateResult,
    G1_alpha_meltdown,
    G2_analysis_gaming,
    G3_plausibility,
    G4_p_hacking,
    get_fired_gates,
    calculate_total_likelihood_ratio,
)

__all__ = [
    # Signal primitives
    "SignalResult",
    "S1_endpoint_changed",
    "S2_underpowered_pivotal", 
    "S3_subgroup_only_no_multiplicity",
    "S4_itt_vs_pp_dropout",
    "S5_implausible_vs_graveyard",
    "S6_many_interims_no_spending",
    "S7_single_arm_where_rct_standard",
    "S8_pvalue_cusp_or_heaping",
    "S9_os_pfs_contradiction",
    "evaluate_all_signals",
    "get_fired_signals",
    "get_high_severity_signals",
    
    # Enhanced gate evaluation system
    "SignalEvidence",
    "GateEval",
    "evaluate_gates",
    "load_gate_config",
    
    # Legacy compatibility
    "GateResult",
    "G1_alpha_meltdown",
    "G2_analysis_gaming",
    "G3_plausibility",
    "G4_p_hacking",
    "get_fired_gates",
    "calculate_total_likelihood_ratio",
]
