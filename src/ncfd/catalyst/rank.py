"""Multi-level ranking system for Phase 10 Catalyst System."""

from __future__ import annotations
from datetime import date
from typing import List, Optional
from dataclasses import dataclass

from .models import RankedTrial


def sort_ranked_trials(trials: List[RankedTrial], today: date) -> List[RankedTrial]:
    """
    Sort trials using multi-level ranking system.
    
    Primary sort: Study card score (1-10 scale)
    Secondary sort: LLM resolution score (1-100 scale) within score bands
    Tertiary sort: Recency and proximity within 3-point score bands
    """
    
    # Group trials into 3-point score bands
    def get_score_band(score: float) -> int:
        """Get score band (1-3, 4-6, 7-10)."""
        if score <= 3:
            return 1
        elif score <= 6:
            return 2
        else:
            return 3
    
    # Sort within each score band
    def sort_within_band(band_trials: List[RankedTrial]) -> List[RankedTrial]:
        """Sort trials within a score band."""
        # Calculate ranking keys for all trials in the band
        for trial in band_trials:
            trial.get_ranking_key(today)
        
        # Sort by: LLM resolution score (desc), proximity (asc), certainty (desc), ticker
        return sorted(band_trials, key=lambda t: (
            -t.llm_resolution_score,  # Higher LLM score first
            t.proximity_score,        # Lower proximity (closer) first
            -t.certainty,             # Higher certainty first
            t.ticker                  # Lexicographic ticker
        ))
    
    # Group trials by score band
    band_1 = []  # Score 1-3
    band_2 = []  # Score 4-6
    band_3 = []  # Score 7-10
    
    for trial in trials:
        band = get_score_band(trial.study_card_score)
        if band == 1:
            band_1.append(trial)
        elif band == 2:
            band_2.append(trial)
        else:
            band_3.append(trial)
    
    # Sort within each band and combine (highest scores first)
    sorted_trials = []
    sorted_trials.extend(sort_within_band(band_3))  # Score 7-10 first
    sorted_trials.extend(sort_within_band(band_2))  # Score 4-6 second
    sorted_trials.extend(sort_within_band(band_1))  # Score 1-3 last
    
    return sorted_trials


def calculate_ranking_confidence(trial: RankedTrial) -> float:
    """
    Calculate confidence in the ranking based on multiple factors.
    
    Returns:
        Confidence score between 0.0 and 1.0
    """
    confidence_factors = []
    
    # Study card score confidence (higher scores = higher confidence)
    if trial.study_card_score > 0:
        score_confidence = min(1.0, trial.study_card_score / 10.0)
        confidence_factors.append(score_confidence)
    
    # LLM resolution confidence
    if trial.llm_resolution_score > 0:
        llm_confidence = min(1.0, trial.llm_resolution_score / 100.0)
        confidence_factors.append(llm_confidence)
    
    # Catalyst window certainty
    if trial.certainty > 0:
        confidence_factors.append(trial.certainty)
    
    # Proximity confidence (closer = higher confidence)
    if trial.proximity_score < 9999:  # Not past window
        proximity_confidence = max(0.1, 1.0 - (trial.proximity_score / 365.0))
        confidence_factors.append(proximity_confidence)
    
    # Calculate weighted average
    if confidence_factors:
        # Weight study card score more heavily
        weights = [0.4, 0.3, 0.2, 0.1]  # Adjust based on importance
        weighted_sum = sum(f * w for f, w in zip(confidence_factors, weights))
        total_weight = sum(weights[:len(confidence_factors)])
        return weighted_sum / total_weight
    
    return 0.5  # Default confidence


def get_ranking_summary(trials: List[RankedTrial]) -> dict:
    """
    Generate summary statistics for ranked trials.
    
    Returns:
        Dictionary with ranking statistics
    """
    if not trials:
        return {
            'total_trials': 0,
            'score_bands': {},
            'avg_confidence': 0.0,
            'avg_proximity': 0.0
        }
    
    # Count trials in each score band
    score_bands = {1: 0, 2: 0, 3: 0}
    for trial in trials:
        if trial.study_card_score <= 3:
            score_bands[1] += 1
        elif trial.study_card_score <= 6:
            score_bands[2] += 1
        else:
            score_bands[3] += 1
    
    # Calculate averages
    avg_confidence = sum(calculate_ranking_confidence(t) for t in trials) / len(trials)
    avg_proximity = sum(t.proximity_score for t in trials if t.proximity_score < 9999) / max(1, len([t for t in trials if t.proximity_score < 9999]))
    
    return {
        'total_trials': len(trials),
        'score_bands': score_bands,
        'avg_confidence': avg_confidence,
        'avg_proximity': avg_proximity,
        'high_priority_count': len([t for t in trials if t.study_card_score >= 7]),
        'medium_priority_count': len([t for t in trials if 4 <= t.study_card_score <= 6]),
        'low_priority_count': len([t for t in trials if t.study_card_score <= 3])
    }


def filter_trials_by_criteria(
    trials: List[RankedTrial],
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    min_confidence: Optional[float] = None,
    max_proximity: Optional[int] = None,
    phases: Optional[List[str]] = None,
    tickers: Optional[List[str]] = None
) -> List[RankedTrial]:
    """
    Filter trials based on various criteria.
    
    Args:
        trials: List of trials to filter
        min_score: Minimum study card score
        max_score: Maximum study card score
        min_confidence: Minimum confidence threshold
        max_proximity: Maximum proximity (days to window)
        phases: List of trial phases to include
        tickers: List of tickers to include
    
    Returns:
        Filtered list of trials
    """
    filtered = trials
    
    if min_score is not None:
        filtered = [t for t in filtered if t.study_card_score >= min_score]
    
    if max_score is not None:
        filtered = [t for t in filtered if t.study_card_score <= max_score]
    
    if min_confidence is not None:
        filtered = [t for t in filtered if calculate_ranking_confidence(t) >= min_confidence]
    
    if max_proximity is not None:
        filtered = [t for t in filtered if t.proximity_score <= max_proximity]
    
    if phases:
        filtered = [t for t in filtered if t.phase in phases]
    
    if tickers:
        filtered = [t for t in filtered if t.ticker in tickers]
    
    return filtered
