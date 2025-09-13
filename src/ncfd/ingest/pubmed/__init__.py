"""
PubMed ingestion module for NCFD.

Provides PubMed E-utilities client, query building, response mapping,
and pipeline orchestration for clinical trial literature processing.
"""

from .client import PubMedClient, PubMedBatchProcessor
from .mapper import PubMedMapper
# from .pipeline import PubMedPipeline  # Moved to pipeline/pubmed_pipeline.py
from .db_service import PubMedDBService, get_db_service
from .normalization import AssetIndicationNormalizer
# Legacy stage_u1 removed - use new retrieval/processing modules

# New retrieval system components
from .retrieval import RetrievalProcessor, RetrievalResult
from .processing import AbstractProcessor, ProcessingResult
# Dual persistence pipeline removed - using simplified approach

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
    
    # Legacy stage processors removed
    
    # New retrieval system components
    "RetrievalProcessor",
    "RetrievalResult",
    "AbstractProcessor",
    "ProcessingResult",
    # Dual persistence pipeline removed
]
