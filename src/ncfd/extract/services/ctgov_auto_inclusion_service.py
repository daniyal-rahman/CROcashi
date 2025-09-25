"""
CT.gov Auto-Inclusion Service

Automatically includes CT.gov trials in document prioritization.
This service finds CT.gov trials that match the entity pack criteria
and creates DocumentCard objects for them, ensuring they get processed
with full text retrieval at runtime.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from ncfd.db.session import session_scope
from ncfd.db.models import Trial, DocumentLink
from ncfd.extract.models.document_card import DocumentCard
from ncfd.entities.entity_pack_service import EntityPack

logger = logging.getLogger(__name__)


@dataclass
class CTgovTrialMatch:
    """Represents a CT.gov trial that matches the entity pack criteria."""
    trial_id: int
    nct_id: str
    title: str
    phase: Optional[str]
    indication: Optional[str]
    asset_names: List[str]
    match_confidence: float
    match_reasons: List[str]


class CTgovAutoInclusionService:
    """
    Service for automatically including CT.gov trials in document prioritization.
    
    This service:
    1. Finds CT.gov trials that match entity pack criteria
    2. Creates DocumentCard objects for these trials
    3. Ensures they get full text retrieval at runtime
    4. Prioritizes them above R/S scored documents
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the CT.gov auto-inclusion service.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.auto_inclusion_config = config.get('ctgov_auto_inclusion', {})
        
        # Configuration values - focused on asset matching only
        self.min_match_confidence = self.auto_inclusion_config.get('min_match_confidence', 0.4)  # Lower threshold since we only match on assets
        self.max_trials_per_entity_pack = self.auto_inclusion_config.get('max_trials_per_entity_pack', 10)
        self.asset_match_required = self.auto_inclusion_config.get('asset_match_required', True)  # Asset match is required
    
    async def get_ctgov_trial_documents(
        self, 
        entity_pack: EntityPack,
        trial_context: Dict[str, Any]
    ) -> List[DocumentCard]:
        """
        Get CT.gov trial documents that should be auto-included.
        
        Args:
            entity_pack: Entity pack containing asset names, indications, etc.
            trial_context: Trial context for additional filtering
            
        Returns:
            List of DocumentCard objects for CT.gov trials
        """
        logger.info("🔍 Searching for CT.gov trials to auto-include based on asset matches...")
        
        try:
            # Find matching CT.gov trials based ONLY on asset names
            matching_trials = await self._find_matching_ctgov_trials(entity_pack, trial_context)
            
            if not matching_trials:
                logger.info("No CT.gov trials found matching asset names for auto-inclusion")
                return []
            
            logger.info(f"Found {len(matching_trials)} CT.gov trials matching asset names for auto-inclusion")
            
            # Convert to DocumentCard objects
            document_cards = []
            for trial_match in matching_trials:
                document_card = await self._create_document_card_from_trial(trial_match, entity_pack)
                if document_card:
                    document_cards.append(document_card)
            
            logger.info(f"Created {len(document_cards)} DocumentCard objects for CT.gov trials")
            return document_cards
            
        except Exception as e:
            logger.error(f"Error in CT.gov auto-inclusion: {e}")
            return []
    
    async def _find_matching_ctgov_trials(
        self, 
        entity_pack: EntityPack,
        trial_context: Dict[str, Any]
    ) -> List[CTgovTrialMatch]:
        """
        Find CT.gov trials that match the entity pack criteria.
        
        Args:
            entity_pack: Entity pack containing search criteria
            trial_context: Additional trial context
            
        Returns:
            List of matching CT.gov trials
        """
        matching_trials = []
        
        try:
            with session_scope() as session:
                # Build query based ONLY on asset/therapy matches
                query = session.query(Trial).filter(
                    Trial.nct_id.isnot(None),  # Only CT.gov trials
                    Trial.status.in_(['Recruiting', 'Active', 'Completed', 'Enrolling by Invitation'])
                )
                
                # ONLY filter by asset names - this is the primary matching criteria
                if entity_pack.asset:
                    asset_names = entity_pack.get_all_asset_terms()
                    # Search in intervention_types or brief_title for asset matches
                    asset_conditions = []
                    for asset_name in asset_names:
                        # Search in trial title
                        asset_conditions.append(
                            Trial.brief_title.ilike(f'%{asset_name}%')
                        )
                        # Search in intervention types
                        asset_conditions.append(
                            Trial.intervention_types.contains([asset_name])
                        )
                        # Search in official title as well
                        asset_conditions.append(
                            Trial.official_title.ilike(f'%{asset_name}%')
                        )
                    
                    if asset_conditions:
                        from sqlalchemy import or_
                        query = query.filter(or_(*asset_conditions))
                else:
                    # No asset names provided - return empty result
                    logger.warning("No asset names provided in entity pack - skipping CT.gov auto-inclusion")
                    return []
                
                # Execute query
                trials = query.limit(self.max_trials_per_entity_pack).all()
                
                # Score and filter trials
                for trial in trials:
                    match = await self._score_trial_match(trial, entity_pack)
                    if match and match.match_confidence >= self.min_match_confidence:
                        matching_trials.append(match)
                
                # Sort by confidence
                matching_trials.sort(key=lambda x: x.match_confidence, reverse=True)
                
        except Exception as e:
            logger.error(f"Error finding CT.gov trials: {e}")
        
        return matching_trials
    
    async def _score_trial_match(
        self, 
        trial: Trial, 
        entity_pack: EntityPack
    ) -> Optional[CTgovTrialMatch]:
        """
        Score how well a CT.gov trial matches the entity pack criteria.
        
        Args:
            trial: CT.gov trial to score
            entity_pack: Entity pack containing criteria
            
        Returns:
            CTgovTrialMatch if match is good enough, None otherwise
        """
        match_reasons = []
        confidence_score = 0.0
        
        # ONLY check asset name matches - this is the primary criteria
        if entity_pack.asset:
            asset_names = entity_pack.get_all_asset_terms()
            for asset_name in asset_names:
                # Check trial title matches
                if asset_name.lower() in trial.brief_title.lower():
                    match_reasons.append(f"Asset '{asset_name}' found in brief title")
                    confidence_score += 0.5
                elif trial.official_title and asset_name.lower() in trial.official_title.lower():
                    match_reasons.append(f"Asset '{asset_name}' found in official title")
                    confidence_score += 0.5
                
                # Check intervention types matches
                if trial.intervention_types and asset_name in trial.intervention_types:
                    match_reasons.append(f"Asset '{asset_name}' found in interventions")
                    confidence_score += 0.4
        else:
            # No asset names - no match possible
            return None
        
        # Only return if we have a reasonable asset match
        if confidence_score < 0.4:
            return None
        
        return CTgovTrialMatch(
            trial_id=trial.trial_id,
            nct_id=trial.nct_id,
            title=trial.brief_title,
            phase=trial.phase,
            indication=trial.indication,
            asset_names=entity_pack.get_all_asset_terms() if entity_pack.asset else [],
            match_confidence=min(confidence_score, 1.0),
            match_reasons=match_reasons
        )
    
    async def _create_document_card_from_trial(
        self, 
        trial_match: CTgovTrialMatch,
        entity_pack: EntityPack
    ) -> Optional[DocumentCard]:
        """
        Create a DocumentCard object from a CT.gov trial match.
        
        Args:
            trial_match: CT.gov trial match
            entity_pack: Entity pack for context
            
        Returns:
            DocumentCard object or None if creation fails
        """
        try:
            # Create DocumentCard with CT.gov trial information
            document_card = DocumentCard(
                doc_id=f"ctgov_{trial_match.trial_id}",  # Unique ID for CT.gov trials
                doc_type="Registry",  # CT.gov trials are registry documents
                title=trial_match.title,
                year=datetime.now().year,  # Use current year as placeholder
                source_id=trial_match.nct_id,  # NCT ID as source ID
                intervention=trial_match.asset_names[0] if trial_match.asset_names else None,
                disease=trial_match.indication,
                abstract=f"CT.gov trial: {trial_match.title}. Match confidence: {trial_match.match_confidence:.2f}. Match reasons: {', '.join(trial_match.match_reasons)}"
            )
            
            return document_card
            
        except Exception as e:
            logger.error(f"Error creating DocumentCard from CT.gov trial {trial_match.trial_id}: {e}")
            return None
