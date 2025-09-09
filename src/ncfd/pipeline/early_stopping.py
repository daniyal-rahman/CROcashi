"""
Early stopping rules for PubMed literature processing.

Implements threshold-based stopping, plateau detection, and resource-based stopping
for the literature processing pipeline.
"""

import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)


def should_stop_early(trial: Dict[str, Any], config: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """
    Determine if processing should stop early for a trial.
    
    Args:
        trial: Trial state dictionary
        config: Configuration dictionary with thresholds
        
    Returns:
        Tuple of (decision, reason) where decision is one of:
        - "continue": Keep processing
        - "stop": Stop processing, maintain current decision
        - "park": Park trial for later review
        - "promote": Promote trial to review queue
    """
    # Top-K guard: do not allow low-confidence parking until top-K relevant docs are examined
    # Expect trial['top_k_guard'] = { 'enabled': bool, 'k': int, 'seen': int, 'completed': bool, 'risk_hit': bool }
    top_k = trial.get('top_k_guard') or {}
    
    # High confidence stops
    if trial.get('p_short', 0) >= config.get('theta_high', 0.80):
        return "promote", "high_confidence"
    
    # Early promote on very high single-doc risk (best S among R>=R2)
    # Check for high S scores even if p_short is low
    best_S_Rge2 = trial.get('best_S_Rge2', 0.0)
    if best_S_Rge2 >= 0.70:  # S3 threshold
        return "promote", "high_shortability_score"
    
    # Top-K guard: if enabled and not completed, force continue
    if top_k.get('enabled') and not top_k.get('completed'):
        # If any risky doc found within top-K, keep going (do not park yet)
        if top_k.get('risk_hit'):
            return "continue", "top_k_risk_guard"
        # If we have not finished reading top-K docs, keep going
        target_k = int(top_k.get('k', 10))
        seen_k = int(top_k.get('seen', 0))
        if seen_k < target_k:
            return "continue", "top_k_incomplete"
    
    if trial.get('p_short', 0) <= config.get('theta_low', 0.20):
        # Only park if we don't have high S scores
        # And only after top-K guard completes without any risk hit
        if best_S_Rge2 < 0.45 and (not top_k.get('enabled') or top_k.get('completed')):  # S2 threshold
            return "park", "low_confidence"
    
    # Plateau detection
    if plateau_detected(trial, config.get('plateau_eps', 0.03)):
        if trial.get('max_expected_utility_next_doc', 1.0) < config.get('delta_min', 0.05):
            return "stop", "utility_plateau"
        else:
            return "stop", "probability_plateau"
    
    # Resource limits
    if trial.get('n_docs_seen', 0) >= config.get('max_abstracts_total', 50):
        return "stop", "document_quota"
    
    if trial.get('processing_time', 0) > config.get('max_processing_time', 2.0):
        return "stop", "time_limit"
    
    return "continue", None


def initialize_top_k_guard(trial: Dict[str, Any], k: int = 10) -> Dict[str, Any]:
    """
    Initialize Top-K guard for a trial.
    
    Args:
        trial: Trial state dictionary
        k: Number of top documents to examine
        
    Returns:
        Updated trial state with top_k_guard initialized
    """
    trial['top_k_guard'] = {
        'enabled': True,
        'k': k,
        'seen': 0,
        'completed': False,
        'risk_hit': False
    }
    return trial


def update_top_k_guard(trial: Dict[str, Any], document: Dict[str, Any], is_top_k: bool = False) -> Dict[str, Any]:
    """
    Update Top-K guard based on new document.
    
    Args:
        trial: Trial state dictionary
        document: New document with R/S scores
        is_top_k: Whether this document is from the top-K ranked set
        
    Returns:
        Updated trial state
    """
    top_k = trial.get('top_k_guard', {})
    
    if not top_k.get('enabled'):
        return trial
    
    if is_top_k:
        # Increment seen count
        top_k['seen'] = top_k.get('seen', 0) + 1
        
        # Check if this document meets risk criteria (R2+ and S1+)
        r_score = document.get('r_score', 0.0)
        s_score = document.get('s_score', 0.0)
        
        if r_score >= 0.55 and s_score >= 0.20:  # R2 and S1 thresholds
            top_k['risk_hit'] = True
            logger.info(f"Risk hit detected in Top-K document: R={r_score:.2f}, S={s_score:.2f}")
        
        # Check if Top-K is complete
        if top_k['seen'] >= top_k.get('k', 10):
            top_k['completed'] = True
            logger.info(f"Top-K guard completed: {top_k['seen']} documents examined, risk_hit={top_k['risk_hit']}")
    
    trial['top_k_guard'] = top_k
    return trial


def plateau_detected(trial: Dict[str, Any], epsilon: float) -> bool:
    """
    Detect if p_short has plateaued (no meaningful progress).
    
    Args:
        trial: Trial state dictionary
        epsilon: Minimum change threshold
        
    Returns:
        True if plateau detected, False otherwise
    """
    p_short_history = trial.get('p_short_history', [])
    
    if len(p_short_history) < 2:
        return False
    
    # Calculate recent changes
    recent_changes = [
        abs(p_short_history[i] - p_short_history[i-1])
        for i in range(1, len(p_short_history))
    ]
    
    # Check last 2 consecutive evaluations
    if len(recent_changes) >= 2:
        last_two_changes = recent_changes[-2:]
        return all(change < epsilon for change in last_two_changes)
    
    return False


def calculate_expected_utility(trial: Dict[str, Any]) -> float:
    """
    Calculate expected utility of processing the next document.
    
    Args:
        trial: Trial state dictionary
        
    Returns:
        Expected utility score (0.0-1.0)
    """
    current_p_short = trial.get('p_short', 0.5)
    n_docs_seen = trial.get('n_docs_seen', 0)
    best_S_Rge2 = trial.get('best_S_Rge2', 0.0)
    
    # Base utility decreases with more documents
    base_utility = max(0.1, 1.0 - (n_docs_seen * 0.05))
    
    # Utility decreases if we have high confidence
    if current_p_short < 0.15 or current_p_short > 0.85:
        confidence_penalty = 0.5
    else:
        confidence_penalty = 0.0
    
    # Utility increases if best S score is high (more uncertainty)
    if best_S_Rge2 > 0.6:
        uncertainty_boost = 0.2
    else:
        uncertainty_boost = 0.0
    
    expected_utility = base_utility - confidence_penalty + uncertainty_boost
    return max(0.0, min(1.0, expected_utility))


def update_trial_state(trial: Dict[str, Any], document: Dict[str, Any], is_top_k: bool = False) -> Dict[str, Any]:
    """
    Update trial state based on new document.
    
    Args:
        trial: Current trial state
        document: New document with R/S scores
        is_top_k: Whether this document is from the top-K ranked set
        
    Returns:
        Updated trial state
    """
    # Increment document count
    trial['n_docs_seen'] = trial.get('n_docs_seen', 0) + 1
    
    # Update best S score among R≥2 documents
    r_score = document.get('r_score', 0.0)
    s_score = document.get('s_score', 0.0)
    
    if r_score >= 0.55:  # R2 threshold
        trial['n_docs_selected'] = trial.get('n_docs_selected', 0) + 1
        if s_score > trial.get('best_S_Rge2', 0.0):
            trial['best_S_Rge2'] = s_score
    
    # Update p_short based on cumulative evidence
    trial = _update_p_short(trial, document)
    
    # Update Top-K guard
    trial = update_top_k_guard(trial, document, is_top_k)
    
    # Update expected utility
    trial['max_expected_utility_next_doc'] = calculate_expected_utility(trial)
    
    # Update processing time (simulate)
    trial['processing_time'] = trial.get('processing_time', 0.0) + 0.1
    
    return trial


def _update_p_short(trial: Dict[str, Any], document: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update p_short based on new document evidence.
    
    Args:
        trial: Trial state
        document: New document
        
    Returns:
        Updated trial state
    """
    current_p_short = trial.get('p_short', 0.0)
    r_tier = document.get('r_tier', 'R0')
    s_score = document.get('s_score', 0.0)
    
    # Weight based on relevance
    if r_tier in ['R3', 'R2']:
        weight = 0.15  # High relevance documents have more weight
    else:
        weight = 0.05  # Lower relevance documents have less weight
    
    # Update p_short
    new_contribution = s_score * weight
    new_p_short = current_p_short + new_contribution
    
    # Keep bounded between 0 and 1
    new_p_short = max(0.0, min(1.0, new_p_short))
    
    trial['p_short'] = new_p_short
    
    # Store in history for plateau detection
    history = trial.get('p_short_history', [])
    history.append(new_p_short)
    trial['p_short_history'] = history
    
    return trial

