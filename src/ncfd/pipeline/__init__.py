"""
Pipeline module for trial failure detection system.

This module provides the complete end-to-end pipeline including document
ingestion, trial version tracking, study card processing, and automated
failure detection workflows.
"""

from .orchestrator import (
    PipelineOrchestrator,
    UnifiedPipelineOrchestrator,  # Alias for backward compatibility
    OrchestrationOutput,
)

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

from .lit_queue import (
    LiteratureQueue,
    TrialQueueItem,
)

from .early_stopping import (
    should_stop_early,
    plateau_detected,
    calculate_expected_utility,
    update_trial_state,
)

from .ctgov_pipeline import CtgovPipeline, CtgovPipelineOutput
from .sec_pipeline import SecPipeline, SecPipelineOutput
from .study_card_pipeline import StudyCardPipeline, StudyCardPipelineOutput
from .pubmed_pipeline import PubMedPipeline, PubMedPipelineOutput
from .asset_resolver import AssetResolver

__all__ = [
    # Main orchestrator
    "PipelineOrchestrator",
    "UnifiedPipelineOrchestrator",
    "OrchestrationOutput",
    
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
    
    # Literature queue management
    "LiteratureQueue",
    "TrialQueueItem",
    
    # Early stopping rules
    "should_stop_early",
    "plateau_detected",
    "calculate_expected_utility",
    "update_trial_state",
    
    # Individual pipelines
    "CtgovPipeline",
    "CtgovPipelineOutput",
    "SecPipeline", 
    "SecPipelineOutput",
    "StudyCardPipeline",
    "StudyCardPipelineOutput",
    "PubMedPipeline",
    "PubMedPipelineOutput",
    "AssetResolver",
]
