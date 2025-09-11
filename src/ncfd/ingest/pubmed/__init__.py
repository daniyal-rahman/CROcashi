"""
PubMed ingestion module for NCFD.

Provides PubMed E-utilities client, query building, response mapping,
and pipeline orchestration for clinical trial literature processing.
"""

from .client import PubMedClient, PubMedBatchProcessor
from .mapper import PubMedMapper
from .pipeline import PubMedPipeline
from .db_service import PubMedDBService, get_db_service
from .normalization import AssetIndicationNormalizer
from .stage_u1 import StageU1Processor, StageU1Result

# New retrieval system components
from .multi_tier_query_builder import MultiTierQueryBuilder
from .policy_engine import RetrievalPolicy, PolicyConfig
from .advanced_scorer import AdvancedDocumentScorer, ScoringConfig
from .guardrails import GuardrailsSystem, GuardrailConfig
from .ctgov_integration import CTgovIntegration, CTgovConfig

__all__ = [
    # Core components
    "PubMedClient",
    "PubMedBatchProcessor", 
    "PubMedMapper",
    "PubMedPipeline",
    "PubMedDBService",
    "get_db_service",
    
    # Normalization
    "AssetIndicationNormalizer",
    
    # Stage processors
    "StageU1Processor", 
    "StageU1Result",
    
    # New retrieval system components
    "MultiTierQueryBuilder",
    "RetrievalPolicy",
    "PolicyConfig",
    "AdvancedDocumentScorer",
    "ScoringConfig",
    "GuardrailsSystem",
    "GuardrailConfig",
    "CTgovIntegration",
    "CTgovConfig"
]
