"""
Extract module for NCFD.

Contains document processing and extraction components:
- Generators: LLM-based content generation (method cards, results factsheets, pattern detection)
- Risk Assessment: Pattern Families risk scoring system
- Retrieval: Document retrieval and processing
- Models: Data models for study cards and evidence
"""

from .generators import (
    LLMStudyCardGenerator, 
    LLMResultsFactsheetGenerator, 
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
    # Generators
    'LLMStudyCardGenerator',
    'LLMResultsFactsheetGenerator', 
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