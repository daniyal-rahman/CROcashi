"""
Entity resolution module for the biotech knowledge graph.

This module provides the core infrastructure for resolving entities
across multiple data sources using a hierarchical matching strategy.
"""

from src.entity_resolution.types import (
    ResolutionResult, EntityType, MatchMethod,
    ExtractedEntity, MatchingContext
)
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.confidence_scorer import ConfidenceScorer
from src.entity_resolution.base_processor import BaseProcessor

__all__ = [
    'ResolutionResult',
    'EntityType',
    'MatchMethod',
    'ExtractedEntity',
    'MatchingContext',
    'EntityResolver',
    'ConfidenceScorer',
    'BaseProcessor',
]

