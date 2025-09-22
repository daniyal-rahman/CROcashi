"""
Clean Pattern Families Scorer

Simple, elegant blended scoring system for F1-F9 families.
No legacy code, no complexity - just clean scoring.
"""

import math
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .models import PatternDetection, PatternScore, SeverityLevel

@dataclass
class FamilyAggregation:
    """Family-level aggregation result."""
    family_id: str
    max_severity: int
    weighted_count: float
    top_patterns: List[str]

class PatternFamilyScorer:
    """Clean, simple Pattern Families scorer."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.family_weights = config['scoring']['family_weights']
        self.llm_weight = config['scoring']['llm_weight']
        self.over_index_weight = config['scoring']['over_index_weight']
        self.severity_weights = config['scoring']['severity_weights']
    
    def score_trial(self,
                   trial_id: str,
                   detections: List[PatternDetection],
                   p_fail_llm: float,
                   uncertainty: float,
                   trial_context: Dict[str, Any]) -> PatternScore:
        """Score a trial using Pattern Families system."""
        
        # 1. Aggregate families
        family_aggregations = self._aggregate_families(detections)
        
        # 2. Calculate family contributions
        family_contributions = self._calculate_family_contributions(family_aggregations)
        
        # 3. Calculate over-index
        over_index = self._calculate_over_index(family_aggregations, trial_context)
        
        # 4. Get top contributing patterns
        top_patterns = self._get_top_patterns(detections)
        
        # 5. Calculate blended score
        score_0_100 = self._calculate_blended_score(
            p_fail_llm, family_contributions, over_index
        )
        
        return PatternScore(
            trial_id=trial_id,
            p_fail_llm=p_fail_llm,
            score_0_100=score_0_100,
            uncertainty=uncertainty,
            family_contributions=family_contributions,
            over_index=over_index,
            top_patterns=top_patterns
        )
    
    def _aggregate_families(self, detections: List[PatternDetection]) -> Dict[str, FamilyAggregation]:
        """Aggregate patterns by family."""
        family_data = {}
        
        for detection in detections:
            family_id = detection.family_id
            
            if family_id not in family_data:
                family_data[family_id] = {
                    'detections': [],
                    'max_severity': 0,
                    'weighted_count': 0.0
                }
            
            family_data[family_id]['detections'].append(detection)
            
            # Update max severity
            family_data[family_id]['max_severity'] = max(
                family_data[family_id]['max_severity'],
                detection.severity.value
            )
            
            # Add to weighted count
            family_data[family_id]['weighted_count'] += self.severity_weights[detection.severity.value]
        
        # Create FamilyAggregation objects
        aggregations = {}
        for family_id, data in family_data.items():
            # Get top patterns (by severity, then confidence)
            top_patterns = sorted(
                data['detections'],
                key=lambda d: (d.severity.value, d.confidence),
                reverse=True
            )[:3]
            
            aggregations[family_id] = FamilyAggregation(
                family_id=family_id,
                max_severity=data['max_severity'],
                weighted_count=data['weighted_count'],
                top_patterns=[d.pattern_id for d in top_patterns]
            )
        
        return aggregations
    
    def _calculate_family_contributions(self, aggregations: Dict[str, FamilyAggregation]) -> Dict[str, float]:
        """Calculate family contribution weights."""
        contributions = {}
        
        for family_id, aggregation in aggregations.items():
            # Get family weight from config
            family_weight = self.family_weights.get(family_id, 0.0)
            
            # Calculate contribution based on weighted count
            # Higher weighted count = higher contribution
            contribution = family_weight * aggregation.weighted_count
            
            contributions[family_id] = contribution
        
        return contributions
    
    def _calculate_over_index(self, aggregations: Dict[str, FamilyAggregation], trial_context: Dict[str, Any]) -> float:
        """Calculate over-index vs historical peers."""
        
        # Sum all family weighted counts
        total_weighted_count = sum(agg.weighted_count for agg in aggregations.values())
        
        # Get historical baseline for this trial type
        baseline = self._get_historical_baseline(trial_context)
        
        if baseline['std'] == 0:
            return 0.0
        
        # Calculate z-score
        over_index = (total_weighted_count - baseline['mean']) / baseline['std']
        
        return over_index
    
    def _get_historical_baseline(self, trial_context: Dict[str, Any]) -> Dict[str, float]:
        """
        Get historical baseline for peer comparison.
        
        Note: This is a placeholder implementation. Historical baseline lookup
        would require access to a database of historical trial pattern scores
        filtered by trial characteristics (phase, indication, etc.).
        
        Args:
            trial_context: Trial context information
            
        Returns:
            Dictionary with 'mean' and 'std' of historical baseline
        """
        # Placeholder implementation - would require historical data access
        return {
            'mean': 2.5,
            'std': 1.2
        }
    
    def _get_top_patterns(self, detections: List[PatternDetection]) -> List[Dict[str, Any]]:
        """Get top contributing patterns."""
        # Sort by severity, then confidence
        sorted_detections = sorted(
            detections,
            key=lambda d: (d.severity.value, d.confidence),
            reverse=True
        )
        
        # Return top 5 patterns
        top_patterns = []
        for detection in sorted_detections[:5]:
            top_patterns.append({
                'pattern_id': detection.pattern_id,
                'severity': detection.severity.value,
                'confidence': detection.confidence,
                'rationale': detection.rationale
            })
        
        return top_patterns
    
    def _calculate_blended_score(self, 
                               p_fail_llm: float, 
                               family_contributions: Dict[str, float],
                               over_index: float) -> int:
        """Calculate final blended score (0-100)."""
        
        # Convert LLM probability to logit
        llm_logit = self._logit(p_fail_llm)
        
        # Calculate family contribution logit
        family_logit = sum(family_contributions.values())
        
        # Blend components
        raw_score = (
            self.llm_weight * llm_logit +
            (1 - self.llm_weight) * family_logit +
            self.over_index_weight * over_index
        )
        
        # Convert to 0-100 scale
        score_0_100 = round(100 * self._sigmoid(raw_score))
        
        # Clamp to valid range
        return max(0, min(100, score_0_100))
    
    def _logit(self, p: float) -> float:
        """Convert probability to logit."""
        if p <= 0:
            return -10.0
        elif p >= 1:
            return 10.0
        else:
            return math.log(p / (1 - p))
    
    def _sigmoid(self, x: float) -> float:
        """Convert logit to probability."""
        return 1 / (1 + math.exp(-x))
