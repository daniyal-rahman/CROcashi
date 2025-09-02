"""
Worker Interfaces Package

Contains abstract interfaces for study card workers to ensure consistency
between different implementation strategies (deterministic vs LLM).
"""

from .denominator_resolver import IDenominatorResolver, DenominatorResult, create_denominator_resolver

__all__ = [
    "IDenominatorResolver",
    "DenominatorResult", 
    "create_denominator_resolver"
]
