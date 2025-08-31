"""
Study Card Schemas Package

JSON schemas for validation of all study card models.
"""

from .base import BASE_SCHEMA
from .document_card import DOCUMENT_CARD_SCHEMA

__all__ = ["BASE_SCHEMA", "DOCUMENT_CARD_SCHEMA", "get_schema"]

def get_schema(name: str):
    # lazy import by name to avoid hard deps at package import time
    if name == "evidence_span":
        from . import evidence_span as mod
        return getattr(mod, "EVIDENCE_SPAN_SCHEMA", None)
    if name == "claim":
        from . import claim as mod
        return getattr(mod, "CLAIM_SCHEMA", None)
    if name == "method_card":
        from . import method_card as mod
        return getattr(mod, "METHOD_CARD_SCHEMA", None)
    if name == "results_factsheet":
        from . import results_factsheet as mod
        return getattr(mod, "RESULTS_FACTHEET_SCHEMA", None)
    if name == "pocket_context":
        from . import pocket_context as mod
        return getattr(mod, "POCKET_CONTEXT_SCHEMA", None)
    if name == "gate_candidate":
        from . import gate_candidate as mod
        return getattr(mod, "GATE_CANDIDATE_SCHEMA", None)
    if name == "gate_spec":
        from . import gate_spec as mod
        return getattr(mod, "GATE_SPEC_SCHEMA", None)
    if name == "gate_assessment":
        from . import gate_assessment as mod
        return getattr(mod, "GATE_ASSESSMENT_SCHEMA", None)
    if name == "decision_record":
        from . import decision_record as mod
        return getattr(mod, "DECISION_RECORD_SCHEMA", None)
    return None
