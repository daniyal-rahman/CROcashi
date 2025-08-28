"""
Pipeline components for document ingestion, processing, and orchestration.
"""

from .ingestion import (
    DocumentIngestionPipeline,
    ingest_document,
    batch_ingest_documents,
    validate_ingested_data,
)

from .tracking import (
    TrialVersionTracker,
    track_trial_changes,
    detect_material_changes,
    generate_change_summary,
)

__all__ = [
    # Document ingestion
    "DocumentIngestionPipeline",
    "ingest_document",
    "batch_ingest_documents", 
    "validate_ingested_data",
    
    # Trial version tracking
    "TrialVersionTracker",
    "track_trial_changes",
    "detect_material_changes",
    "generate_change_summary",
]
