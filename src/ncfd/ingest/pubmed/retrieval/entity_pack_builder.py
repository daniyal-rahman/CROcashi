"""
Entity Pack Builder - Step 1 of retrieval pipeline.

Creates canonical entities & alias tables for consistent retrieval across all retrievers.
Implements the entity pack schema for multi-tier query building.
"""

import logging
from typing import List, Optional, Dict, Any
from ....entities.schema import EntityPack, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, DateRangeInfo

logger = logging.getLogger(__name__)


class EntityPackBuilder:
    """Builds entity packs for consistent retrieval."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize entity pack builder."""
        self.config = config or {}
        
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
            # Default company info
            company_canonical = company_name or "Unknown Company"
            company_alias_list = company_aliases or []
            
            # Default asset info
            asset_canonical = asset_aliases[0] if asset_aliases else "unknown"
            asset_alias_list = asset_aliases[1:] if len(asset_aliases) > 1 else []
            
            # Default mechanism info (can be customized per asset)
            mechanism_targets = self._get_mechanism_targets(asset_canonical)
            
            # Default indication info
            indication_primary = [indication_terms[0]] if indication_terms else ["Alzheimer Disease"]
            indication_synonyms = indication_terms[1:] if len(indication_terms) > 1 else []
            
            # Registry info
            nct_ids = [trial_nct] if trial_nct else []
            
            # Create entity pack
            entity_pack = EntityPack(
                entity_id=f"trial_{trial_nct or 'unknown'}",
                company=CompanyInfo(
                    canonical=company_canonical,
                    aliases=company_alias_list
                ),
                asset=AssetInfo(
                    canonical=asset_canonical,
                    aliases=asset_alias_list
                ),
                mechanism=MechanismInfo(
                    targets=mechanism_targets
                ),
                indications=IndicationInfo(
                    primary=indication_primary,
                    synonyms=indication_synonyms
                ),
                registries=RegistryInfo(
                    nct_ids=nct_ids
                ),
                publishers=PublisherInfo(
                    sponsor_strings=[]
                ),
                date_ranges=DateRangeInfo(
                    active_since=2020
                )
            )
            
            logger.info(f"Created entity pack for {entity_pack.entity_id}")
            return entity_pack
            
        except Exception as e:
            logger.error(f"Error creating entity pack: {e}")
            return None
    
    def _get_mechanism_targets(self, asset_name: str) -> List[str]:
        """Get mechanism targets based on asset name."""
        # Comprehensive mechanism targets for simufilam/PTI-125
        if "simufilam" in asset_name.lower() or "pti" in asset_name.lower():
            return [
                "filamin A", "FLNA", "filamin-A", "filamin A protein",
                "amyloid", "tau", "amyloid-beta", "Aβ", "beta-amyloid",
                "amyloid precursor protein", "APP", "presenilin"
            ]
        elif "alzheimer" in asset_name.lower():
            return ["amyloid", "tau", "amyloid-beta", "Aβ", "beta-amyloid"]
        else:
            return []
    
    def update_entity_pack_with_nct_ids(self, entity_pack: EntityPack, nct_ids: List[str]) -> EntityPack:
        """Update entity pack with discovered NCT IDs."""
        if not nct_ids:
            return entity_pack
            
        # Add new NCT IDs to existing ones
        existing_nct_ids = set(entity_pack.registries.nct_ids)
        new_nct_ids = set(nct_ids)
        all_nct_ids = list(existing_nct_ids.union(new_nct_ids))
        
        # Create updated entity pack
        updated_pack = EntityPack(
            entity_id=entity_pack.entity_id,
            company=entity_pack.company,
            asset=entity_pack.asset,
            mechanism=entity_pack.mechanism,
            indications=entity_pack.indications,
            registries=RegistryInfo(nct_ids=all_nct_ids),
            publishers=entity_pack.publishers,
            date_ranges=entity_pack.date_ranges
        )
        
        logger.info(f"Updated entity pack with {len(new_nct_ids)} new NCT IDs")
        return updated_pack
