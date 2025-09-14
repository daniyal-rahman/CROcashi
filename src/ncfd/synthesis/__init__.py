"""
Synthesis module for generating trial narratives.
"""

from .evidence_constrained_synthesis import (
    EvidenceConstrainedSynthesizer,
    SynthesisError,
    SynthesisDoc,
    Ref,
    Sentence,
    SynthesisConfig
)
from .independent_llm_analysis import (
    IndependentLLMAnalysis,
    trigger_independent_llm_analysis_sync,
    LiteratureReviewAgent,
    IndependentAnalysisAgent,
    LiteratureResult,
    IndependentAnalysis
)

__all__ = [
    "EvidenceConstrainedSynthesizer",
    "SynthesisError", 
    "SynthesisDoc",
    "Ref",
    "Sentence",
    "SynthesisConfig",
    "IndependentLLMAnalysis",
    "trigger_independent_llm_analysis_sync",
    "LiteratureReviewAgent",
    "IndependentAnalysisAgent",
    "LiteratureResult",
    "IndependentAnalysis"
]
