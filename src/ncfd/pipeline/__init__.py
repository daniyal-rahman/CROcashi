"""
Pipeline module for trial failure detection system.

This module provides the complete end-to-end pipeline including document
ingestion, trial version tracking, study card processing, and automated
failure detection workflows.
"""

from .orchestrator import (
    PipelineOrchestrator,
    OrchestrationOutput,
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

from .ctgov_pipeline import CtgovPipeline, CtgovPipelineOutput
from .sec_pipeline import SecPipeline, SecPipelineOutput
from .study_card_pipeline import StudyCardPipeline, StudyCardPipelineOutput
from .pubmed_pipeline import PubMedPipeline, PubMedPipelineOutput
from .asset_resolver import AssetResolver

__all__ = [
    # Main orchestrator
    "PipelineOrchestrator",
    "OrchestrationOutput",
    
    # Trial version tracking
    "TrialVersionTracker",
    "track_trial_changes",
    "detect_material_changes",
    "generate_change_summary",
    
    # Literature queue management
    "LiteratureQueue",
    "TrialQueueItem",
    
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
