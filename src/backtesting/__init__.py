"""
Backtesting infrastructure for biotech signal validation.

This package provides tools for validating short-selling signals
using historical catalyst events and stock price reactions.
"""

from src.backtesting.catalyst_extractor import (
    extract_fda_catalysts,
    extract_trial_catalysts,
    compute_stock_reaction,
    load_catalysts,
)

__all__ = [
    'extract_fda_catalysts',
    'extract_trial_catalysts',
    'compute_stock_reaction',
    'load_catalysts',
]
