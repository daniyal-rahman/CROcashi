"""
Literature utility scoring for the pruning strategy.

This module implements the U0 (metadata-only) and U1 (abstract-based) utility scoring
algorithms that determine which documents should be promoted to the next stage
of processing.
"""

import re
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ScoringConfig:
    """Configuration for literature scoring."""
    # Metadata scoring weights
    phase_3_weight: float = 0.25
    randomization_weight: float = 0.20
    double_blind_weight: float = 0.10
    nct_mention_weight: float = 0.10
    rct_type_weight: float = 0.20
    recency_weight: float = 0.15
    
    # Abstract scoring weights
    negative_signal_weight: float = 0.45
    positive_signal_weight: float = 0.00  # Robust signals lower short-utility
    sample_size_weight: float = 0.15
    structural_weight: float = 0.10
    
    # Recency parameters
    recency_months: int = 18
    
    # Thresholds
    tau_abstract: float = 0.40  # Recommended value for 30-60% drop rate
    theta_high: float = 0.80
    theta_low: float = 0.20
    delta_min: float = 0.05


class LiteratureScorer:
    """
    Implements utility scoring for literature documents.
    
    Based on the pruning strategy document, this class provides:
    - U0: Metadata-only scoring (0-1)
    - U1: Abstract-based scoring (0-1)
    - Trial priority calculation
    - Uncertainty computation
    """
    
    def __init__(self, config: Optional[ScoringConfig] = None):
        """
        Initialize literature scorer.
        
        Args:
            config: Scoring configuration, uses defaults if None
        """
        self.config = config or ScoringConfig()
        
        # Compile regex patterns for efficiency
        self._compile_patterns()
        
        logger.info("Literature scorer initialized with config: %s", self.config)
    
    def _compile_patterns(self):
        """Compile regex patterns for document analysis."""
        # Abstract scoring patterns - expanded for Checkpoint 2
        self._neg_pattern = re.compile(
            r"(did not meet|no (?:significant|statistical) (?:difference|benefit)|"
            r"failed to|non-?significant|ns[,\. ]|futility|"
            r"primary endpoint was not met|primary endpoint not met|"
            r"failed to achieve|did not achieve|"
            r"did not demonstrate superiority|superiority not demonstrated|"
            r"non-inferiority not shown|non-inferiority not demonstrated|"
            r"stopped early for futility|stopped early due to futility|"
            r"confidence interval.*crossed 1\.0|hazard ratio.*~1|"
            r"subgroup.*only.*significant|post.?hoc.*only.*significant|"
            r"primary endpoint.*not met|endpoint.*not met|"
            r"not met.*primary endpoint|not met.*endpoint)", 
            re.IGNORECASE
        )
        
        self._pos_pattern = re.compile(
            r"(met (?:the )?primary endpoint|statistically significant|"
            r"significant improvement|superior(?:ity)?|"
            r"primary endpoint was met|primary endpoint met|"
            r"demonstrated superiority|achieved superiority|"
            r"demonstrated non-inferiority|achieved non-inferiority|"
            r"met.*primary endpoint|met.*endpoint)", 
            re.IGNORECASE
        )
        
        self._sample_size_pattern = re.compile(
            r"\b(?:n\s*=\s*\d{2,4}|patients?\s+\d{2,4})\b", 
            re.IGNORECASE
        )
        
        self._structural_pattern = re.compile(
            r"(randomi[sz]ed|double[-\s]?blind|placebo|active comparator)", 
            re.IGNORECASE
        )
    
    def score_metadata(self, title: str, article_type: str, year: int, 
                      catalyst_year: int) -> float:
        """
        Score document based on metadata only (U0 score).
        
        Args:
            title: Document title
            article_type: Type of article (e.g., "Randomized Controlled Trial")
            year: Publication year
            catalyst_year: Year of the catalyst event
            
        Returns:
            U0 score between 0.0 and 1.0
        """
        if not title or not article_type:
            return 0.0
        
        t = title.lower()
        score = 0.0
        
        # Phase 3 boost
        if "phase 3" in t or "phase iii" in t:
            score += self.config.phase_3_weight
        
        # Randomization boost
        if "random" in t:
            score += self.config.randomization_weight
        
        # Double-blind boost
        if "double-blind" in t or "double blind" in t:
            score += self.config.double_blind_weight
        
        # NCT ID mention boost
        if "nct0" in t:
            score += self.config.nct_mention_weight
        
        # Article type boost
        article_type_lower = article_type.lower()
        if article_type_lower in {"randomized controlled trial", "clinical trial"}:
            score += self.config.rct_type_weight
        elif article_type_lower in {"review", "meta-analysis"}:
            score += 0.05  # Small boost for reviews
        elif article_type_lower in {"letter", "editorial", "corrigendum"}:
            score -= 0.10  # Penalty for non-research content
        
        # Recency boost (±18 months from catalyst)
        if abs(year - catalyst_year) <= 1:
            score += self.config.recency_weight
        
        # Penalize preclinical/animal studies
        if any(keyword in t for keyword in ["mouse", "rat", "animal", "preclinical", "in vitro"]):
            score -= 0.20
        
        # Penalize protocols and corrigenda
        if any(keyword in t for keyword in ["protocol", "corrigendum", "erratum"]):
            score -= 0.15
        
        return max(0.0, min(1.0, score))
    
    def score_abstract(self, abstract: str) -> float:
        """
        Score document based on abstract content (U1 score).
        
        Args:
            abstract: Document abstract text
            
        Returns:
            U1 score between 0.0 and 1.0
        """
        if not abstract:
            return 0.0
        
        score = 0.0
        
        # Strong negative signals (increase short utility)
        if self._neg_pattern.search(abstract):
            score += self.config.negative_signal_weight
        
        # Strong positive signals (robust signals lower short utility)
        if self._pos_pattern.search(abstract):
            score += self.config.positive_signal_weight
        
        # Sample size information
        if self._sample_size_pattern.search(abstract):
            score += self.config.sample_size_weight
        
        # Structural cues (randomization, blinding, etc.)
        if self._structural_pattern.search(abstract):
            score += self.config.structural_weight
        
        # Additional negative signals
        if re.search(r"(confidence interval.*crossed 1\.0|hazard ratio.*~1)", abstract, re.IGNORECASE):
            score += 0.20
        
        if re.search(r"(subgroup.*only.*significant|post.?hoc)", abstract, re.IGNORECASE):
            score += 0.15
        
        return max(0.0, min(1.0, score))
    
    def compute_uncertainty(self, p_short: float) -> float:
        """
        Compute uncertainty measure for a trial.
        
        Args:
            p_short: Probability of short trial (0.0 to 1.0)
            
        Returns:
            Uncertainty measure (0.0 to 0.25, where 0.25 is maximum uncertainty)
        """
        if p_short <= 0.0 or p_short >= 1.0:
            return 0.0
        
        # Uncertainty is highest when p_short = 0.5
        # Use p * (1-p) formula for binomial uncertainty
        return p_short * (1.0 - p_short)
    
    def calculate_trial_priority(self, trial_data: Dict[str, Any]) -> float:
        """
        Calculate trial priority score for queue management.
        
        Args:
            trial_data: Dictionary containing trial information:
                - time_to_catalyst: days until catalyst
                - p_short: current posterior probability
                - uncertainty: current uncertainty measure
                - u_max_next: utility of next best document
                
        Returns:
            Priority score (higher is more important)
        """
        # Extract values with defaults
        time_to_catalyst = trial_data.get('time_to_catalyst', 365)  # Default to 1 year
        p_short = trial_data.get('p_short', 0.5)
        uncertainty = trial_data.get('uncertainty', 0.25)
        u_max_next = trial_data.get('u_max_next', 0.0)
        
        # Weights for priority calculation
        w1 = 0.4  # Time to catalyst weight
        w2 = 0.4  # P(short) * uncertainty weight
        w3 = 0.2  # Next document utility weight
        
        # Time component: sooner gets higher priority
        time_weight = max(0.1, 1.0 / (1.0 + time_to_catalyst / 30.0))  # Normalize to 30-day scale
        
        # Uncertainty component: explore if uncertain & promising
        uncertainty_component = p_short * uncertainty
        
        # Next document utility component
        utility_component = u_max_next
        
        # Calculate weighted priority
        priority = (w1 * time_weight + 
                   w2 * uncertainty_component + 
                   w3 * utility_component)
        
        return max(0.0, min(1.0, priority))
    
    def should_promote_to_abstract(self, u0_score: float) -> bool:
        """
        Determine if document should be promoted to abstract fetching.
        
        Args:
            u0_score: U0 metadata score
            
        Returns:
            True if document should get abstract
        """
        # Use a threshold based on the pruning strategy
        # This could be configurable per trial or globally
        return u0_score >= 0.3
    
    def should_promote_to_full_text(self, u1_score: float) -> bool:
        """
        Determine if document should be promoted to full text fetching.
        
        Args:
            u1_score: U1 abstract score
            
        Returns:
            True if document should get full text
        """
        return u1_score >= self.config.tau_abstract
    
    def get_scoring_summary(self, u0_score: float, u1_score: float) -> Dict[str, Any]:
        """
        Get a summary of scoring decisions.
        
        Args:
            u0_score: U0 metadata score
            u1_score: U1 abstract score (None if not available)
            
        Returns:
            Dictionary with scoring summary and recommendations
        """
        summary = {
            'u0_score': u0_score,
            'u1_score': u1_score,
            'promote_to_abstract': self.should_promote_to_abstract(u0_score),
            'promote_to_full_text': False,
            'recommendation': 'metadata_only'
        }
        
        if summary['promote_to_abstract'] and u1_score is not None:
            summary['promote_to_full_text'] = self.should_promote_to_full_text(u1_score)
            
            if summary['promote_to_full_text']:
                summary['recommendation'] = 'full_text'
            else:
                summary['recommendation'] = 'abstract_only'
        
        return summary
