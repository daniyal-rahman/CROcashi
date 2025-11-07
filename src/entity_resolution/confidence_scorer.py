"""
Confidence scoring for entity matching.

Implements the scoring formula specified in the requirements:
    base_score = trigram_similarity(name1, name2)
    context_boost = 0.0
    if same_company: context_boost += 0.10
    if same_disease: context_boost += 0.05
    if same_mechanism: context_boost += 0.05
    if same_target: context_boost += 0.05
    if same_time_period: context_boost += 0.05
    final_score = min(1.0, base_score + context_boost)
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Calculates match confidence scores using base similarity and context boosting.
    
    Decision thresholds:
        >= 0.90: Auto-match (high confidence)
        0.75 - 0.89: Auto-match but flag for periodic review
        0.60 - 0.74: Needs manual review before matching
        < 0.60: Likely different entities
    """
    
    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.90
    MEDIUM_CONFIDENCE_THRESHOLD = 0.75
    LOW_CONFIDENCE_THRESHOLD = 0.60
    
    # Context boost amounts
    SAME_COMPANY_BOOST = 0.10
    SAME_DISEASE_BOOST = 0.05
    SAME_MECHANISM_BOOST = 0.05
    SAME_TARGET_BOOST = 0.05
    SAME_TIME_PERIOD_BOOST = 0.05
    
    # Time period window (months)
    TIME_PERIOD_WINDOW_MONTHS = 6
    
    def __init__(self, session: Session):
        """
        Initialize confidence scorer.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    def calculate_trigram_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate trigram similarity between two strings using PostgreSQL.
        
        Args:
            text1: First string
            text2: Second string
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not text1 or not text2:
            return 0.0
        
        # Normalize strings
        text1 = self._normalize_text(text1)
        text2 = self._normalize_text(text2)
        
        # Exact match after normalization
        if text1 == text2:
            return 1.0
        
        # Use PostgreSQL pg_trgm similarity
        from sqlalchemy import text
        query = text("SELECT similarity(:text1, :text2)")
        result = self.session.execute(query, {"text1": text1, "text2": text2})
        similarity = result.scalar()
        
        return float(similarity) if similarity is not None else 0.0
    
    def calculate_score(
        self,
        name1: str,
        name2: str,
        context1: Optional[Dict[str, Any]] = None,
        context2: Optional[Dict[str, Any]] = None,
    ) -> tuple[float, List[str]]:
        """
        Calculate final confidence score with context boosting.
        
        Args:
            name1: First entity name
            name2: Second entity name
            context1: Context for first entity
            context2: Context for second entity
            
        Returns:
            Tuple of (final_score, reasons) where reasons explain the score
        """
        context1 = context1 or {}
        context2 = context2 or {}
        
        # Calculate base trigram similarity
        base_score = self.calculate_trigram_similarity(name1, name2)
        
        # Calculate context boosts
        context_boost = 0.0
        reasons = [f"Base trigram similarity: {base_score:.2f}"]
        
        # Check for same company
        if self._same_entities(context1.get('company_ids', []), context2.get('company_ids', [])):
            context_boost += self.SAME_COMPANY_BOOST
            reasons.append(f"Same company context: +{self.SAME_COMPANY_BOOST:.2f}")
        
        # Check for same disease
        if self._same_entities(context1.get('disease_ids', []), context2.get('disease_ids', [])):
            context_boost += self.SAME_DISEASE_BOOST
            reasons.append(f"Same disease context: +{self.SAME_DISEASE_BOOST:.2f}")
        
        # Check for same mechanism
        if self._same_entities(context1.get('mechanism_ids', []), context2.get('mechanism_ids', [])):
            context_boost += self.SAME_MECHANISM_BOOST
            reasons.append(f"Same mechanism context: +{self.SAME_MECHANISM_BOOST:.2f}")
        
        # Check for same target
        if self._same_entities(context1.get('target_ids', []), context2.get('target_ids', [])):
            context_boost += self.SAME_TARGET_BOOST
            reasons.append(f"Same target context: +{self.SAME_TARGET_BOOST:.2f}")
        
        # Check for same time period
        if self._same_time_period(context1.get('date'), context2.get('date')):
            context_boost += self.SAME_TIME_PERIOD_BOOST
            reasons.append(f"Same time period: +{self.SAME_TIME_PERIOD_BOOST:.2f}")
        
        # Calculate final score (capped at 1.0)
        final_score = min(1.0, base_score + context_boost)
        
        if context_boost > 0:
            reasons.append(f"Total context boost: +{context_boost:.2f}")
        reasons.append(f"Final score: {final_score:.2f}")
        
        return final_score, reasons
    
    def classify_confidence(self, score: float) -> str:
        """
        Classify confidence score into category.
        
        Args:
            score: Confidence score (0.0 to 1.0)
            
        Returns:
            Category: 'high', 'medium', 'low', or 'very_low'
        """
        if score >= self.HIGH_CONFIDENCE_THRESHOLD:
            return 'high'
        elif score >= self.MEDIUM_CONFIDENCE_THRESHOLD:
            return 'medium'
        elif score >= self.LOW_CONFIDENCE_THRESHOLD:
            return 'low'
        else:
            return 'very_low'
    
    def should_auto_match(self, score: float) -> bool:
        """
        Determine if score is high enough for automatic matching.
        
        Args:
            score: Confidence score
            
        Returns:
            True if should auto-match, False otherwise
        """
        return score >= self.MEDIUM_CONFIDENCE_THRESHOLD
    
    def needs_review(self, score: float) -> bool:
        """
        Determine if match needs manual review.
        
        Args:
            score: Confidence score
            
        Returns:
            True if needs review, False otherwise
        """
        return self.LOW_CONFIDENCE_THRESHOLD <= score < self.MEDIUM_CONFIDENCE_THRESHOLD
    
    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text for comparison.
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized text
        """
        import re
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove common company suffixes
        suffixes = [
            r'\s+inc\.?$', r'\s+incorporated$', r'\s+corp\.?$', r'\s+corporation$',
            r'\s+ltd\.?$', r'\s+limited$', r'\s+llc$', r'\s+plc$',
            r'\s+gmbh$', r'\s+ag$', r'\s+sa$', r'\s+nv$'
        ]
        for suffix in suffixes:
            text = re.sub(suffix, '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        # Remove special characters but keep spaces and hyphens
        text = re.sub(r'[^\w\s\-]', '', text)
        
        return text.strip()
    
    @staticmethod
    def _same_entities(list1: List[Any], list2: List[Any]) -> bool:
        """
        Check if two lists have any common entities.
        
        Args:
            list1: First list of entity IDs
            list2: Second list of entity IDs
            
        Returns:
            True if there's at least one common entity
        """
        if not list1 or not list2:
            return False
        
        set1 = set(str(x) for x in list1 if x)
        set2 = set(str(x) for x in list2 if x)
        
        return bool(set1 & set2)
    
    def _same_time_period(
        self,
        date1: Optional[datetime],
        date2: Optional[datetime]
    ) -> bool:
        """
        Check if two dates are within the same time period (6 months).
        
        Args:
            date1: First date
            date2: Second date
            
        Returns:
            True if dates are within 6 months of each other
        """
        if not date1 or not date2:
            return False
        
        # Convert to datetime if needed
        if isinstance(date1, str):
            try:
                date1 = datetime.fromisoformat(date1)
            except (ValueError, AttributeError):
                return False
        
        if isinstance(date2, str):
            try:
                date2 = datetime.fromisoformat(date2)
            except (ValueError, AttributeError):
                return False
        
        # Calculate difference
        delta = abs((date1 - date2).days)
        threshold_days = self.TIME_PERIOD_WINDOW_MONTHS * 30
        
        return delta <= threshold_days

