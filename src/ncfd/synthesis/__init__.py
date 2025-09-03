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
from .gpt5_thinking_hook import (
    GPT5ThinkingHook,
    trigger_gpt5_analysis_sync,
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
    "GPT5ThinkingHook",
    "trigger_gpt5_analysis_sync",
    "LiteratureReviewAgent",
    "IndependentAnalysisAgent",
    "LiteratureResult",
    "IndependentAnalysis"
]
