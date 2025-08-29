"""
PubMed ingestion module for NCFD.

Provides PubMed E-utilities client, query building, response mapping,
and pipeline orchestration for clinical trial literature processing.
"""

from .client import PubMedClient, PubMedBatchProcessor
from .query_builder import PubMedQueryBuilder
from .trial_query_builder import TrialQueryBuilder
from .mapper import PubMedMapper
from .pipeline import PubMedPipeline
from .normalization import AssetIndicationNormalizer
from .stage_u0 import StageU0Processor, StageU0Result
from .stage_u1 import StageU1Processor, StageU1Result

__all__ = [
    # Core components
    "PubMedClient",
    "PubMedBatchProcessor", 
    "PubMedQueryBuilder",
    "TrialQueryBuilder",
    "PubMedMapper",
    "PubMedPipeline",
    
    # Normalization
    "AssetIndicationNormalizer",
    
    # Stage processors
    "StageU0Processor",
    "StageU0Result",
    "StageU1Processor", 
    "StageU1Result"
]
