"""
Backtest package for NCFD pipeline evaluation.
"""

from .outcomes import compute_outcome_severity, OutcomeSeverity

__all__ = [
    "compute_outcome_severity",
    "OutcomeSeverity"
]
