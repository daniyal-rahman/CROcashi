"""
EvidenceField Model

Common field class for LLM-generated evidence with quotes.
Used by MethodCard, ResultsFactsheet, and GateAssessment generators.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class EvidenceField:
    """A field with its evidence quote - used across all LLM generators."""
    field_name: str
    value: Any
    evidence_quote: str
    confidence: float = 0.8
