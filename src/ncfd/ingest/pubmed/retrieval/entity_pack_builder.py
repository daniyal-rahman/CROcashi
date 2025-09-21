"""
Entity Pack Builder - Step 1 of retrieval pipeline.

Creates canonical entities & alias tables for consistent retrieval across all retrievers.
Implements the entity pack schema for multi-tier query building.
"""

import logging
import unicodedata
from typing import List, Optional, Dict, Any, Set
from ....entities.schema import EntityPack, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, DateRangeInfo
from ....entities.entity_pack_service import EntityPackService

logger = logging.getLogger(__name__)


class EntityPackBuilder:
    """Builds entity packs for consistent retrieval."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize entity pack builder."""
        self.config = config or {}
        # Use the centralized service
        self.entity_pack_service = EntityPackService(config)
    
        
    def create_entity_pack(
        self, 
        asset_aliases: List[str], 
        indication_terms: List[str], 
        trial_nct: Optional[str] = None,
        trial_phase: Optional[str] = None,
        company_name: Optional[str] = None,
        company_aliases: Optional[List[str]] = None
    ) -> Optional[EntityPack]:
        """
        Create entity pack for multi-tier queries.
        
        Args:
            asset_aliases: List of asset names/aliases
            indication_terms: List of disease/indication terms
            trial_nct: Optional NCT ID for exact matching
            trial_phase: Optional trial phase for filtering
            company_name: Optional company name
            company_aliases: Optional company aliases
            
        Returns:
            EntityPack object or None if creation fails
        """
        try:
            logger.info(f"Creating entity pack with asset_aliases={asset_aliases}, indication_terms={indication_terms}")
            
            # Use the centralized service to create entity pack from parameters
            entity_pack = self.entity_pack_service.create_from_parameters(
                asset_aliases=asset_aliases,
                indication_terms=indication_terms,
                trial_nct=trial_nct,
                trial_phase=trial_phase,
                company_name=company_name,
                company_aliases=company_aliases
            )
            
            if entity_pack:
                logger.info(f"Created entity pack for {entity_pack.entity_id}")
            else:
                logger.error("Failed to create entity pack")
            
            return entity_pack
            
        except Exception as e:
            logger.error(f"Error creating entity pack: {e}")
            return None
    
    def update_entity_pack_with_nct_ids(self, entity_pack: EntityPack, nct_ids: List[str]) -> EntityPack:
        """Update entity pack with discovered NCT IDs."""
        return self.entity_pack_service.update_entity_pack_with_nct_ids(entity_pack, nct_ids)
