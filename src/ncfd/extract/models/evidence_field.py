"""
EvidenceField Model

Common field class for LLM-generated evidence with quotes.
Used by StudyCard, Factsheet, and GateAssessment extractors.
"""

from dataclasses import dataclass
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class EvidenceField:
    """A field with its evidence quote - used across all LLM generators."""
    field_name: str
    value: Any
    evidence_quote: str
    confidence: float = 0.8
    
    def __post_init__(self):
        """Validate and clean the evidence field after initialization."""
        # Ensure evidence_quote is a string
        if not isinstance(self.evidence_quote, str):
            if self.evidence_quote is None:
                self.evidence_quote = ""
            elif isinstance(self.evidence_quote, (int, float)):
                # If it's a number, it's likely malformed - log warning and set to empty
                logger.warning(f"EvidenceField initialized with numeric evidence_quote '{self.evidence_quote}' - setting to empty string")
                self.evidence_quote = ""
            else:
                # Try to convert other types to string
                self.evidence_quote = str(self.evidence_quote)
        
        # Ensure field_name is a string
        if not isinstance(self.field_name, str):
            self.field_name = str(self.field_name) if self.field_name is not None else ""
        
        # Validate confidence is between 0 and 1
        if not isinstance(self.confidence, (int, float)) or self.confidence < 0.0 or self.confidence > 1.0:
            logger.warning(f"Invalid confidence value '{self.confidence}' - setting to 0.8")
            self.confidence = 0.8
