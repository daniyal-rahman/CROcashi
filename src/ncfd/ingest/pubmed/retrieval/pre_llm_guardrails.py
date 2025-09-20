"""
Pre-LLM Guardrails System for PubMed Documents

This module implements enhanced guardrails that filter documents before expensive LLM processing.
Incorporates all improvements from S score analysis and guardrails analysis.

Key Features:
- Off-topic content filtering (pain therapeutics, COVID, cancer)
- Early stage risk detection (novel, candidate, phase 3)
- Controversy signal detection (comment, editorial, suggested)
- Surrogate endpoint detection (biomarker, mechanism, lymphocyte)
- Relevance checking (asset/indication matching)
- Cost efficiency (filter before LLM processing)
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from ncfd.entities.schema import EntityPack
from ncfd.db.models import Document, DocumentText

logger = logging.getLogger(__name__)


@dataclass
class PreLLMGuardrailsConfig:
    """Configuration for pre-LLM guardrails system."""
    
    # Off-topic content filtering
    reject_off_topic: bool = True
    off_topic_keywords: List[str] = None
    
    # Risk-based filtering
    reject_high_risk: bool = True
    high_risk_threshold: float = 0.6
    
    # Relevance requirements
    require_relevance: bool = True
    require_asset_or_indication: bool = True
    
    # Logging
    log_decisions: bool = True
    log_rejections: bool = True
    
    def __post_init__(self):
        if self.off_topic_keywords is None:
            self.off_topic_keywords = [
                'pain therapeutics', 'covid', 'vaccine', 'coronavirus',
                'cancer', 'oncology', 'diabetes', 'cardiology', 'hypertension',
                'depression', 'anxiety', 'psychiatry', 'mental health'
            ]


@dataclass
class PreLLMGuardrailsResult:
    """Result of pre-LLM guardrails check."""
    
    should_process: bool
    reason: str
    risk_score: float
    risk_components: Dict[str, Any]
    rejection_details: Optional[Dict[str, Any]] = None


class PreLLMGuardrailsSystem:
    """
    Enhanced guardrails system for filtering documents before LLM processing.
    
    Incorporates all improvements from S score analysis and guardrails analysis:
    - Off-topic content filtering
    - Early stage risk detection  
    - Controversy signal detection
    - Surrogate endpoint detection
    - Relevance checking
    """
    
    def __init__(self, config: PreLLMGuardrailsConfig):
        self.config = config
        self.rejection_counts = {
            'off_topic': 0,
            'high_risk': 0,
            'irrelevant': 0,
            'non_scientific': 0
        }
        logger.info(f"Initialized pre-LLM guardrails system with config: {config}")
    
    def should_process_document(self, document: Document, entity_pack: EntityPack) -> PreLLMGuardrailsResult:
        """
        Determine if document should be processed with LLM.
        
        Args:
            document: Document to check
            entity_pack: Entity pack for validation context
            
        Returns:
            PreLLMGuardrailsResult with decision and details
        """
        # Check if entity_pack is None
        if entity_pack is None:
            logger.warning("Entity pack is None, skipping guardrails checks")
            return PreLLMGuardrailsResult(
                should_process=True,
                risk_score=0.0,
                reason="No entity pack available",
                risk_components={},
                rejection_details={}
            )
        
        # Get document content
        title = document.title or ""
        abstract = ""
        if document.text and document.text.abstract_text:
            abstract = document.text.abstract_text
        
        text = f"{title} {abstract}".lower()
        
        # Calculate risk score using our improved S score logic
        risk_score, risk_components = self._calculate_risk_score(text)
        
        # Apply guardrails checks
        rejection_details = {}
        
        # 1. Check for off-topic content
        if self.config.reject_off_topic:
            off_topic_found = [kw for kw in self.config.off_topic_keywords if kw in text]
            if off_topic_found:
                rejection_details['off_topic'] = off_topic_found
                self.rejection_counts['off_topic'] += 1
                if self.config.log_rejections:
                    logger.info(f"Rejecting off-topic document: {title[:50]}... (keywords: {off_topic_found})")
                return PreLLMGuardrailsResult(
                    should_process=False,
                    reason=f"Off-topic content detected: {off_topic_found}",
                    risk_score=risk_score,
                    risk_components=risk_components,
                    rejection_details=rejection_details
                )
        
        # 2. Check for non-scientific content
        non_scientific_keywords = ['editorial', 'opinion', 'letter to editor', 'commentary']
        non_scientific_found = [kw for kw in non_scientific_keywords if kw in text]
        if non_scientific_found:
            rejection_details['non_scientific'] = non_scientific_found
            self.rejection_counts['non_scientific'] += 1
            if self.config.log_rejections:
                logger.info(f"Rejecting non-scientific document: {title[:50]}... (keywords: {non_scientific_found})")
            return PreLLMGuardrailsResult(
                should_process=False,
                reason=f"Non-scientific content detected: {non_scientific_found}",
                risk_score=risk_score,
                risk_components=risk_components,
                rejection_details=rejection_details
            )
        
        # 3. Check for high-risk early stage content
        if self.config.reject_high_risk and risk_score > self.config.high_risk_threshold:
            rejection_details['high_risk'] = {
                'risk_score': risk_score,
                'threshold': self.config.high_risk_threshold,
                'components': risk_components
            }
            self.rejection_counts['high_risk'] += 1
            if self.config.log_rejections:
                logger.info(f"Rejecting high-risk document: {title[:50]}... (risk: {risk_score:.2f})")
            return PreLLMGuardrailsResult(
                should_process=False,
                reason=f"High-risk early stage content (risk: {risk_score:.2f})",
                risk_score=risk_score,
                risk_components=risk_components,
                rejection_details=rejection_details
            )
        
        # 4. Check for relevance to trial
        if self.config.require_relevance:
            relevance_result = self._check_relevance(text, entity_pack)
            if not relevance_result['is_relevant']:
                rejection_details['irrelevant'] = relevance_result
                self.rejection_counts['irrelevant'] += 1
                if self.config.log_rejections:
                    logger.info(f"Rejecting irrelevant document: {title[:50]}... (no asset/indication match)")
                return PreLLMGuardrailsResult(
                    should_process=False,
                    reason="No relevance to trial (no asset or indication match)",
                    risk_score=risk_score,
                    risk_components=risk_components,
                    rejection_details=rejection_details
                )
        
        # Document passed all checks
        if self.config.log_decisions:
            logger.info(f"Approving document for LLM processing: {title[:50]}... (risk: {risk_score:.2f})")
        
        return PreLLMGuardrailsResult(
            should_process=True,
            reason="Passed all guardrails checks",
            risk_score=risk_score,
            risk_components=risk_components
        )
    
    def _calculate_risk_score(self, text: str) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate risk score using our improved S score logic.
        
        Incorporates all improvements from S score analysis:
        - Early stage indicators (novel, candidate, phase 3)
        - Controversy signals (comment, editorial, suggested)
        - Surrogate endpoints (biomarker, mechanism, lymphocyte)
        - Unproven mechanisms (preclinical, in vitro, in vivo)
        """
        # High-risk keywords (0.2 points each)
        high_risk_keywords = ['comment', 'novel', 'candidate', 'suggested', 'preliminary']
        
        # Medium-risk keywords (0.1 points each)
        medium_risk_keywords = [
            'small molecule', 'phase 3', 'mechanism', 'biomarker',
            'lymphocyte', 'in vitro', 'in vivo', 'preclinical'
        ]
        
        # Count matches
        high_count = sum(1 for kw in high_risk_keywords if kw in text)
        medium_count = sum(1 for kw in medium_risk_keywords if kw in text)
        
        # Calculate risk score
        risk_score = (high_count * 0.2) + (medium_count * 0.1)
        risk_score = min(1.0, risk_score)
        
        # Find specific keywords found
        high_found = [kw for kw in high_risk_keywords if kw in text]
        medium_found = [kw for kw in medium_risk_keywords if kw in text]
        
        components = {
            'high_risk_keywords': high_found,
            'medium_risk_keywords': medium_found,
            'high_count': high_count,
            'medium_count': medium_count,
            'risk_score': risk_score
        }
        
        return risk_score, components
    
    def _check_relevance(self, text: str, entity_pack: EntityPack) -> Dict[str, Any]:
        """
        Check if document is relevant to the trial.
        
        Args:
            text: Document text (title + abstract)
            entity_pack: Entity pack for validation context
            
        Returns:
            Dict with relevance information
        """
        # Get asset terms
        if entity_pack.asset is None:
            return {"relevance_score": 0.0, "asset_found": [], "indication_found": []}
        
        asset_terms = entity_pack.asset.aliases + [entity_pack.asset.canonical]
        asset_found = [term for term in asset_terms if term.lower() in text]
        
        # Get indication terms
        indication_terms = entity_pack.indications.primary + entity_pack.indications.synonyms
        indication_found = [term for term in indication_terms if term.lower() in text]
        
        # Check for mechanism targets (e.g., "filamin A" for simufilam)
        mechanism_terms = []
        if hasattr(entity_pack.mechanism, 'targets'):
            mechanism_terms = entity_pack.mechanism.targets
        mechanism_found = [term for term in mechanism_terms if term.lower() in text]
        
        # Document is relevant if it mentions asset, indication, or mechanism
        is_relevant = bool(asset_found or indication_found or mechanism_found)
        
        return {
            'is_relevant': is_relevant,
            'asset_found': asset_found,
            'indication_found': indication_found,
            'mechanism_found': mechanism_found,
            'asset_terms_checked': asset_terms,
            'indication_terms_checked': indication_terms,
            'mechanism_terms_checked': mechanism_terms
        }
    
    def get_rejection_summary(self) -> Dict[str, int]:
        """Get summary of rejection counts."""
        return self.rejection_counts.copy()
    
    def reset_counts(self):
        """Reset rejection counts."""
        self.rejection_counts = {
            'off_topic': 0,
            'high_risk': 0,
            'irrelevant': 0,
            'non_scientific': 0
        }
