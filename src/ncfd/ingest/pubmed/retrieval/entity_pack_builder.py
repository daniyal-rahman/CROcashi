"""
Entity Pack Builder - Step 1 of retrieval pipeline.

Creates canonical entities & alias tables for consistent retrieval across all retrievers.
Implements the entity pack schema for multi-tier query building.
"""

import logging
import unicodedata
from typing import List, Optional, Dict, Any, Set
from ....entities.schema import EntityPack, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, DateRangeInfo

logger = logging.getLogger(__name__)


class EntityPackBuilder:
    """Builds entity packs for consistent retrieval."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize entity pack builder."""
        self.config = config or {}
        # Configuration for entity cleaning
        self.max_tier_c_terms = self.config.get('max_tier_c_terms', 10)  # Cap mechanism terms
        self.enable_deduplication = self.config.get('enable_deduplication', True)
        self.enable_normalization = self.config.get('enable_normalization', True)
    
    def _normalize_term(self, term: str) -> str:
        """Normalize a term for deduplication (casefold + ASCII normalize)."""
        if not term:
            return ""
        # Unicode normalization (NFC) + casefold + strip
        normalized = unicodedata.normalize('NFC', term.strip().lower())
        return normalized
    
    def _deduplicate_and_normalize(self, terms: List[str]) -> List[str]:
        """Remove duplicates and normalize terms."""
        if not self.enable_deduplication and not self.enable_normalization:
            return terms
        
        # Track seen normalized forms to avoid duplicates
        seen_normalized: Set[str] = set()
        deduplicated: List[str] = []
        
        for term in terms:
            if not term or not term.strip():
                continue
                
            normalized_key = self._normalize_term(term) if self.enable_normalization else term.lower()
            
            if normalized_key not in seen_normalized:
                seen_normalized.add(normalized_key)
                # Keep original casing/formatting for the final list
                deduplicated.append(term.strip())
        
        return deduplicated
    
    def _limit_tier_c_terms(self, mechanism_terms: List[str]) -> List[str]:
        """Limit Tier C (mechanism) terms to avoid overly broad queries."""
        if len(mechanism_terms) <= self.max_tier_c_terms:
            return mechanism_terms
        
        # Keep top canonical synonyms (could be ranked by frequency/importance in future)
        limited = mechanism_terms[:self.max_tier_c_terms]
        logger.info(f"Limited Tier C mechanism terms from {len(mechanism_terms)} to {len(limited)}")
        return limited
        
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
            # Clean and deduplicate inputs
            asset_aliases_clean = self._deduplicate_and_normalize(asset_aliases or [])
            indication_terms_clean = self._deduplicate_and_normalize(indication_terms or [])
            company_aliases_clean = self._deduplicate_and_normalize(company_aliases or [])
            
            # Default company info
            company_canonical = company_name or "Unknown Company"
            company_alias_list = company_aliases_clean
            
            # Default asset info
            asset_canonical = asset_aliases_clean[0] if asset_aliases_clean else "unknown"
            asset_alias_list = asset_aliases_clean
            
            # Debug logging for entity pack creation
            logger.info(f"DEBUG: Creating entity pack with asset_aliases={asset_aliases_clean} (cleaned from {asset_aliases})")
            logger.info(f"DEBUG: asset_canonical='{asset_canonical}'")
            
            # Default mechanism info (can be customized per asset)
            mechanism_targets_raw = self._get_mechanism_targets(asset_canonical)
            mechanism_targets_clean = self._deduplicate_and_normalize(mechanism_targets_raw)
            mechanism_targets = self._limit_tier_c_terms(mechanism_targets_clean)
            logger.info(f"DEBUG: mechanism_targets={mechanism_targets} (limited from {len(mechanism_targets_raw)} raw terms)")
            
            # Default indication info
            indication_primary = [indication_terms_clean[0]] if indication_terms_clean else ["Alzheimer Disease"]
            indication_synonyms = indication_terms_clean
            
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
        logger.info(f"DEBUG: Getting mechanism targets for asset_name='{asset_name}'")
        
        # Comprehensive mechanism targets for simufilam/PTI-125
        if "simufilam" in asset_name.lower() or "pti" in asset_name.lower():
            targets = [
                "filamin A", "FLNA", "filamin-A", "filamin A protein",
                "amyloid", "tau", "amyloid-beta", "Aβ", "beta-amyloid",
                "amyloid precursor protein", "APP", "presenilin"
            ]
            logger.info(f"DEBUG: Found simufilam/PTI match, returning {len(targets)} targets: {targets}")
            return targets
        elif "alzheimer" in asset_name.lower():
            targets = ["amyloid", "tau", "amyloid-beta", "Aβ", "beta-amyloid"]
            logger.info(f"DEBUG: Found Alzheimer match, returning {len(targets)} targets: {targets}")
            return targets
        else:
            logger.warning(f"DEBUG: No mechanism targets found for asset_name='{asset_name}', returning empty list")
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
