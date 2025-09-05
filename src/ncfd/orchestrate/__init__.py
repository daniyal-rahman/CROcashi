"""
Orchestration module for NCFD.

Handles global trial queue management, early stopping rules, and pipeline coordination.
"""

from .lit_queue import LiteratureQueue, TrialQueueItem
from .early_stopping import should_stop_early, plateau_detected, calculate_expected_utility, update_trial_state

__all__ = [
    "LiteratureQueue",
    "TrialQueueItem", 
    "should_stop_early",
    "plateau_detected",
    "calculate_expected_utility",
    "update_trial_state"
]
