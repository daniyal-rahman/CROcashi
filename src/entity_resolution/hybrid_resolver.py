"""
Hybrid entity resolver combining rule-based matching with LLM validation.

This module provides a hybrid approach that uses the rule-based matcher first,
then validates medium-confidence matches with an optional LLM.
"""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.llm_matcher import LLMEntityMatcher, LLMMatchDecision
from src.entity_resolution.types import (
    ExtractedEntity, ResolutionResult, ResolutionStatus, MatchMethod
)
from src.config.feature_flags import FeatureFlags

logger = logging.getLogger(__name__)


class HybridEntityResolver:
    """
    Hybrid entity resolver combining rule-based + LLM.
    
    Strategy:
    1. Try rule-based matching first (fast, free)
    2. If high confidence (≥0.90) → auto-match
    3. If low confidence (<0.60) → create new or review
    4. If medium confidence (0.60-0.89) → validate with LLM (if enabled)
    
    The LLM is optional and controlled by feature flags. When disabled,
    the system behaves exactly like the rule-based resolver.
    """
    
    def __init__(self, session: Session):
        """
        Initialize hybrid resolver.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.rule_based = EntityResolver(session)
        
        # Initialize LLM matcher (may be unavailable)
        self.llm_enabled = FeatureFlags.USE_LLM_VALIDATION
        self.llm_matcher = None
        
        if self.llm_enabled:
            self._init_llm_matcher()
        else:
            logger.info("LLM validation is disabled (USE_LLM_VALIDATION=false)")
    
    def _init_llm_matcher(self):
        """Initialize LLM matcher if enabled."""
        try:
            self.llm_matcher = LLMEntityMatcher(
                model_path=FeatureFlags.LLM_MODEL_PATH
            )
            if self.llm_matcher.is_available():
                logger.info("✓ LLM matcher initialized and available")
            else:
                logger.warning("⚠️  LLM matcher initialized but model not loaded")
        except Exception as e:
            logger.error(f"✗ Failed to initialize LLM matcher: {e}")
            self.llm_matcher = None
    
    def resolve(self, entity: ExtractedEntity) -> ResolutionResult:
        """
        Resolve entity using hybrid approach.
        
        Args:
            entity: Extracted entity to resolve
        
        Returns:
            ResolutionResult with match details
        """
        # Stage 1: Rule-based matching
        rule_result = self.rule_based.resolve(entity)
        
        logger.info(
            f"Rule-based result for '{entity.name}': "
            f"status={rule_result.status.value}, "
            f"confidence={rule_result.confidence_score:.2f}"
        )
        
        # High confidence → trust rule-based
        if rule_result.confidence_score >= FeatureFlags.LLM_INVOKE_MAX_CONFIDENCE:
            logger.info("✓ High confidence, auto-matching")
            return rule_result
        
        # Low confidence → create new or needs review
        if rule_result.confidence_score < FeatureFlags.LLM_INVOKE_MIN_CONFIDENCE:
            logger.info("✓ Low confidence, creating candidate for review")
            return rule_result
        
        # Medium confidence → validate with LLM if available
        if self._can_use_llm():
            logger.info("→ Medium confidence, validating with LLM")
            return self._validate_with_llm(entity, rule_result)
        else:
            logger.info("✓ Medium confidence but LLM not available, creating candidate")
            return rule_result
    
    def _can_use_llm(self) -> bool:
        """Check if LLM validation is available."""
        return (
            self.llm_enabled and 
            self.llm_matcher is not None and 
            self.llm_matcher.is_available()
        )
    
    def _validate_with_llm(
        self, 
        entity: ExtractedEntity, 
        rule_result: ResolutionResult
    ) -> ResolutionResult:
        """Validate medium-confidence match with LLM."""
        
        # Get entity name for comparison
        entity_name = self._get_entity_name(rule_result, entity)
        
        # Ask LLM
        llm_decision = self.llm_matcher.match_entities(
            candidate_text=entity.name,
            entity_name=entity_name,
            entity_type=entity.entity_type.value,
            context=entity.context,
            rule_confidence=rule_result.confidence_score
        )
        
        logger.info(
            f"LLM decision: match={llm_decision.match}, "
            f"confidence={llm_decision.confidence:.2f}, "
            f"reasoning='{llm_decision.reasoning}'"
        )
        
        # Combine scores if LLM agrees
        if llm_decision.match:
            final_confidence = self._combine_confidences(
                rule_result.confidence_score,
                llm_decision.confidence
            )
            
            logger.info(f"Combined confidence: {final_confidence:.2f}")
            
            if final_confidence >= FeatureFlags.AUTO_MATCH_THRESHOLD:
                return ResolutionResult(
                    status=ResolutionStatus.HIGH_CONFIDENCE,
                    entity_id=rule_result.entity_id,
                    confidence_score=final_confidence,
                    match_method=MatchMethod.HYBRID_LLM,
                    reasoning=self._build_hybrid_reasoning(
                        rule_result, llm_decision, final_confidence
                    )
                )
        
        # LLM disagrees or confidence still too low → review
        return ResolutionResult(
            status=ResolutionStatus.NEEDS_REVIEW,
            candidates=rule_result.candidates,
            confidence_score=rule_result.confidence_score,
            match_method=MatchMethod.HYBRID_LLM,
            reasoning=f"LLM validation inconclusive. {llm_decision.reasoning}"
        )
    
    def _get_entity_name(self, rule_result: ResolutionResult, entity: ExtractedEntity) -> str:
        """Get entity name from rule result or candidates."""
        # If we have an entity_id, query the database
        if rule_result.entity_id:
            return self._query_entity_name(entity.entity_type.value, rule_result.entity_id)
        
        # Otherwise use first candidate if available
        if rule_result.candidates:
            return rule_result.candidates[0].entity_name
        
        # Fallback to extracted entity name
        return entity.name
    
    def _query_entity_name(self, entity_type: str, entity_id: UUID) -> str:
        """Query database for entity name."""
        from database.models.entities import Company, Drug, Disease, Institution
        from database.models.clinical import ClinicalTrial
        
        try:
            if entity_type == 'company':
                entity = self.session.query(Company).filter(Company.company_id == entity_id).first()
                return entity.name if entity else "Unknown"
            elif entity_type == 'drug':
                entity = self.session.query(Drug).filter(Drug.drug_id == entity_id).first()
                return entity.primary_name if entity else "Unknown"
            elif entity_type == 'disease':
                entity = self.session.query(Disease).filter(Disease.disease_id == entity_id).first()
                return entity.disease_name if entity else "Unknown"
            elif entity_type == 'institution':
                entity = self.session.query(Institution).filter(Institution.institution_id == entity_id).first()
                return entity.name if entity else "Unknown"
            elif entity_type == 'trial':
                entity = self.session.query(ClinicalTrial).filter(ClinicalTrial.trial_id == entity_id).first()
                return entity.trial_title if entity else "Unknown"
        except Exception as e:
            logger.error(f"Error querying entity name: {e}")
        
        return "Unknown"
    
    def _combine_confidences(self, rule_conf: float, llm_conf: float) -> float:
        """Combine rule-based and LLM confidences using weighted average."""
        rule_weight = 1.0 - FeatureFlags.LLM_CONFIDENCE_WEIGHT
        llm_weight = FeatureFlags.LLM_CONFIDENCE_WEIGHT
        
        combined = rule_conf * rule_weight + llm_conf * llm_weight
        
        logger.debug(
            f"Combining: rule={rule_conf:.2f} (weight={rule_weight:.2f}), "
            f"llm={llm_conf:.2f} (weight={llm_weight:.2f}) → {combined:.2f}"
        )
        
        return combined
    
    def _build_hybrid_reasoning(
        self,
        rule_result: ResolutionResult,
        llm_decision: LLMMatchDecision,
        final_confidence: float
    ) -> str:
        """Build reasoning string combining both methods."""
        reasoning = (
            f"Hybrid match (confidence={final_confidence:.2f}): "
            f"Rule-based={rule_result.confidence_score:.2f} ({rule_result.match_method.value}), "
            f"LLM={llm_decision.confidence:.2f} (model={llm_decision.model_name}). "
            f"LLM reasoning: {llm_decision.reasoning}"
        )
        return reasoning
    
    def register_entity(self, entity: ExtractedEntity, entity_id: UUID) -> None:
        """
        Register an entity in the underlying resolver's cache.
        
        Pass-through method to ensure cache works when using hybrid resolver.
        
        Args:
            entity: ExtractedEntity that was resolved/created
            entity_id: UUID of the entity
        """
        self.rule_based.register_entity(entity, entity_id)

