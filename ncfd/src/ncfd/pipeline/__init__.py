"""
Pipeline module for trial failure detection system.

This module provides the complete end-to-end pipeline including document
ingestion, trial version tracking, study card processing, and automated
failure detection workflows.
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

from .processing import (
    StudyCardProcessor,
    process_study_card,
    extract_trial_metadata,
    validate_study_card,
)

from .workflow import (
    FailureDetectionWorkflow,
    run_failure_detection,
    batch_process_trials,
    generate_failure_report,
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
    
    # Study card processing
    "StudyCardProcessor",
    "process_study_card",
    "extract_trial_metadata",
    "validate_study_card",
    
    # Complete workflow
    "FailureDetectionWorkflow",
    "run_failure_detection",
    "batch_process_trials",
    "generate_failure_report",
]
