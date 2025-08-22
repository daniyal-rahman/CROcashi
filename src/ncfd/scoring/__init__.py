"""
Scoring module for trial failure detection.

This module provides the advanced scoring system that calculates trial failure
probabilities using calibrated likelihood ratios from gates, prior failure rates,
and posterior probability calculations with stop rules.
"""

from .score import (
    # New advanced scoring system
    AdvancedScoringEngine,
    StopRuleHit,
    
    # Legacy compatibility
    ScoreResult,
    ScoringEngine,
)

from .calibrate import (
    LikelihoodRatioCalibrator,
    PriorRateCalibrator,
    calibrate_scoring_system,
    get_calibrated_config,
)

__all__ = [
    # Advanced scoring system
    "AdvancedScoringEngine",
    "StopRuleHit",
    
    # Legacy compatibility
    "ScoreResult",
    "ScoringEngine",
    
    # Calibration
    "LikelihoodRatioCalibrator",
    "PriorRateCalibrator",
    "calibrate_scoring_system",
    "get_calibrated_config",
]
