"""
Orchestration module for NCFD.

Handles global trial queue management, early stopping rules, and pipeline coordination.
"""

from .lit_queue import LiteratureQueue
from .early_stopping import EarlyStoppingRules

__all__ = [
    "LiteratureQueue",
    "EarlyStoppingRules"
]
