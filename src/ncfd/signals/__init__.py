"""
Signal Evaluation System

This module provides S1-S9 signal detection and G1-G4 gate evaluation.
"""

from .primitives import (
    S1_endpoint_changed, S2_underpowered_pivotal, S3_subgroup_only_no_multiplicity,
    S4_itt_vs_pp_dropout, S5_implausible_vs_graveyard, S6_many_interims_no_spending,
    S7_single_arm_where_rct_standard, S8_pvalue_cusp_or_heaping, S9_os_pfs_contradiction
)
from .gates import evaluate_all_gates
from .scoring import score_trial, get_default_prior_pi

__all__ = [
    'S1_endpoint_changed', 'S2_underpowered_pivotal', 'S3_subgroup_only_no_multiplicity',
    'S4_itt_vs_pp_dropout', 'S5_implausible_vs_graveyard', 'S6_many_interims_no_spending',
    'S7_single_arm_where_rct_standard', 'S8_pvalue_cusp_or_heaping', 'S9_os_pfs_contradiction',
    'evaluate_all_gates', 'score_trial', 'get_default_prior_pi'
]
