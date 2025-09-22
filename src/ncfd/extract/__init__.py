"""
Extract module for NCFD.

Contains document processing and extraction components:
- Extractors: LLM-based content extraction (study cards, factsheets, pattern detection)
- Risk Assessment: Pattern Families risk scoring system
- Retrieval: Document retrieval and processing
- Models: Data models for study cards and evidence
"""

from .generators import (
    LLMStudyCardExtractor, 
    LLMFactsheetExtractor, 
    PatternFamilyDetector
)
from .risk_assessment import (
    PatternFamilyScorer,
    PatternDetection,
    PatternScore,
    SeverityLevel
)
from .retrieval import (
    EnhancedRetriever,
    build_retriever
)

__all__ = [
    # Extractors
    'LLMStudyCardExtractor',
    'LLMFactsheetExtractor', 
    'PatternFamilyDetector',
    # Risk Assessment
    'PatternFamilyScorer',
    'PatternDetection',
    'PatternScore',
    'SeverityLevel',
    # Retrieval
    'EnhancedRetriever',
    'build_retriever'
]