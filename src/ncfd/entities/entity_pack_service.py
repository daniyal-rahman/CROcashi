"""
Centralized Entity Pack Service

This module provides a unified service for creating entity packs from various sources,
eliminating duplication between the orchestrator and retrieval pipeline.
"""

import logging
import unicodedata
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass

from .schema import EntityPack, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, DateRangeInfo
from ..db.session import session_scope
from ..db.models import Asset, Trial, Company

logger = logging.getLogger(__name__)


@dataclass
class EntityPackSource:
    """Source data for entity pack creation."""
    asset_names: Optional[List[str]] = None
    asset_canonical: Optional[str] = None
    asset_aliases: Optional[List[str]] = None
    company_name: Optional[str] = None
    company_canonical: Optional[str] = None
    company_aliases: Optional[List[str]] = None
    indication_terms: Optional[List[str]] = None
    indication_primary: Optional[List[str]] = None
    indication_synonyms: Optional[List[str]] = None
    trial_nct: Optional[str] = None
    trial_id: Optional[int] = None
    trial_phase: Optional[str] = None
    active_since: Optional[int] = None


class EntityPackService:
    """Centralized service for creating entity packs from various sources."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize entity pack service."""
        self.config = config or {}
        # Configuration for entity cleaning
        self.max_tier_c_terms = self.config.get('max_tier_c_terms', 10)  # Cap mechanism terms
        self.enable_deduplication = self.config.get('enable_deduplication', True)
        self.enable_normalization = self.config.get('enable_normalization', True)
        self.logger = logging.getLogger(__name__)
    
    def create_from_trial(self, trial_id: int, asset_names: Optional[List[str]] = None, 
                         indications: Optional[List[str]] = None) -> Optional[EntityPack]:
        """Create entity pack from trial data in database."""
        try:
            with session_scope() as session:
                # Get trial with related data
                trial = session.query(Trial).filter(Trial.trial_id == trial_id).first()
                if not trial:
                    self.logger.error(f"Trial {trial_id} not found")
                    return None
                
                # Extract company information
                company_canonical = trial.sponsor or "Unknown Company"
                company_aliases = [company_canonical.lower()] if company_canonical else []
                
                # Extract asset information
                if asset_names:
                    asset_canonical = asset_names[0] if asset_names else "Unknown Asset"
                    asset_aliases = asset_names
                    self.logger.info(f"Using provided asset names: {asset_names}")
                else:
                    # Try to get asset from trial intervention types
                    if trial.intervention_types:
                        asset_canonical = trial.intervention_types[0] if isinstance(trial.intervention_types, list) else str(trial.intervention_types)
                        asset_aliases = [asset_canonical.lower()]
                    else:
                        asset_canonical = "Unknown Asset"
                        asset_aliases = ["unknown"]
                    self.logger.info(f"Using trial intervention types: {trial.intervention_types}")
                
                # Extract indication information
                if indications:
                    indication_primary = [indications[0]] if indications else ["Unknown"]
                    indication_synonyms = indications
                    self.logger.info(f"Using provided indications: {indications}")
                else:
                    indication_primary = [trial.indication] if trial.indication else ["Unknown"]
                    indication_synonyms = [trial.indication.lower()] if trial.indication else ["unknown"]
                    self.logger.info(f"Using trial indication: {trial.indication}")
                
                # Create source data
                source = EntityPackSource(
                    asset_canonical=asset_canonical,
                    asset_aliases=asset_aliases,
                    company_canonical=company_canonical,
                    company_aliases=company_aliases,
                    indication_primary=indication_primary,
                    indication_synonyms=indication_synonyms,
                    trial_nct=trial.nct_id,
                    trial_id=trial_id,
                    active_since=trial.first_posted_date.year if trial.first_posted_date else 2020
                )
                
                return self._create_entity_pack(source)
                
        except Exception as e:
            self.logger.error(f"Error creating entity pack from trial {trial_id}: {e}")
            return None
    
    def create_from_parameters(self, asset_aliases: List[str], indication_terms: List[str],
                              trial_nct: Optional[str] = None, trial_phase: Optional[str] = None,
                              company_name: Optional[str] = None, company_aliases: Optional[List[str]] = None) -> Optional[EntityPack]:
        """Create entity pack from provided parameters."""
        try:
            # Normalize asset information
            asset_canonical = asset_aliases[0] if asset_aliases else "Unknown Asset"
            asset_alias_list = self._deduplicate_and_normalize(asset_aliases)
            
            # Normalize company information
            company_canonical = company_name or "Unknown Company"
            company_alias_list = self._deduplicate_and_normalize(company_aliases or [company_canonical])
            
            # Normalize indication information
            indication_primary = [indication_terms[0]] if indication_terms else ["Unknown"]
            indication_synonyms = self._deduplicate_and_normalize(indication_terms)
            
            # Create source data
            source = EntityPackSource(
                asset_canonical=asset_canonical,
                asset_aliases=asset_alias_list,
                company_canonical=company_canonical,
                company_aliases=company_alias_list,
                indication_primary=indication_primary,
                indication_synonyms=indication_synonyms,
                trial_nct=trial_nct,
                trial_phase=trial_phase,
                active_since=2020
            )
            
            return self._create_entity_pack(source)
            
        except Exception as e:
            self.logger.error(f"Error creating entity pack from parameters: {e}")
            return None
    
    def _create_entity_pack(self, source: EntityPackSource) -> Optional[EntityPack]:
        """Create entity pack from source data."""
        try:
            # Get mechanism targets
            mechanism_targets_raw = self._get_mechanism_targets(source.asset_canonical)
            mechanism_targets_clean = self._deduplicate_and_normalize(mechanism_targets_raw)
            mechanism_targets = self._limit_tier_c_terms(mechanism_targets_clean)
            
            # Registry info
            nct_ids = [source.trial_nct] if source.trial_nct else []
            
            # Create entity pack
            entity_pack = EntityPack(
                entity_id=f"trial_{source.trial_nct or source.trial_id or 'unknown'}",
                company=CompanyInfo(
                    canonical=source.company_canonical,
                    aliases=source.company_aliases or []
                ),
                asset=AssetInfo(
                    canonical=source.asset_canonical,
                    aliases=source.asset_aliases or []
                ),
                mechanism=MechanismInfo(
                    targets=mechanism_targets
                ),
                indications=IndicationInfo(
                    primary=source.indication_primary or ["Unknown"],
                    synonyms=source.indication_synonyms or []
                ),
                registries=RegistryInfo(
                    nct_ids=nct_ids
                ),
                publishers=PublisherInfo(
                    sponsor_strings=[source.company_canonical] if source.company_canonical else []
                ),
                date_ranges=DateRangeInfo(
                    active_since=source.active_since or 2020
                )
            )
            
            self.logger.info(f"Created entity pack {entity_pack.entity_id}")
            return entity_pack
            
        except Exception as e:
            self.logger.error(f"Error creating entity pack: {e}")
            return None
    
    def _get_mechanism_targets(self, asset_name: str) -> List[str]:
        """Get mechanism targets based on asset name from database."""
        try:
            with session_scope() as session:
                # Try to find asset by canonical name first
                asset = session.query(Asset).filter(
                    Asset.names.op('->>')('canonical').ilike(f'%{asset_name}%')
                ).first()
                
                # If not found by canonical, try by INN
                if not asset:
                    asset = session.query(Asset).filter(
                        Asset.names.op('->>')('inn').ilike(f'%{asset_name}%')
                    ).first()
                
                # If still not found, try by aliases
                if not asset:
                    asset = session.query(Asset).filter(
                        Asset.names.op('?')('aliases')
                    ).filter(
                        Asset.names.op('->')('aliases').op('@>')('"' + asset_name + '"')
                    ).first()
                
                if asset:
                    targets = []
                    
                    # Extract target information
                    if asset.target:
                        targets.append(asset.target)
                    
                    # Extract mechanism of action information
                    if asset.moa:
                        # Split MOA by common delimiters and clean up
                        moa_parts = asset.moa.replace(',', ';').replace('|', ';').split(';')
                        for part in moa_parts:
                            cleaned = part.strip()
                            if cleaned and cleaned not in targets:
                                targets.append(cleaned)
                    
                    # If we have targets from database, return them
                    if targets:
                        self.logger.info(f"Found mechanism targets for asset '{asset_name}': {targets}")
                        return targets
                
                # Fallback to hardcoded mappings for known assets
                asset_lower = asset_name.lower()
                if "simufilam" in asset_lower or "pti-125" in asset_lower:
                    return ["filamin A", "FLNA", "filamin-A", "filamin A protein", "amyloid", "tau", "amyloid-beta", "Aβ", "beta-amyloid", "amyloid precursor protein", "APP", "presenilin"]
                elif "aducanumab" in asset_lower:
                    return ["amyloid", "amyloid-beta", "Aβ", "beta-amyloid", "amyloid precursor protein", "APP"]
                elif "lecanemab" in asset_lower:
                    return ["amyloid", "amyloid-beta", "Aβ", "beta-amyloid", "amyloid precursor protein", "APP"]
                else:
                    self.logger.warning(f"No mechanism targets found for asset '{asset_name}' in database or fallback mappings")
                    return []
                    
        except Exception as e:
            self.logger.error(f"Error querying mechanism targets for asset '{asset_name}': {e}")
            # Fallback to hardcoded mappings on error
            asset_lower = asset_name.lower()
            if "simufilam" in asset_lower or "pti-125" in asset_lower:
                return ["filamin A", "FLNA", "filamin-A", "filamin A protein", "amyloid", "tau", "amyloid-beta", "Aβ", "beta-amyloid", "amyloid precursor protein", "APP", "presenilin"]
            elif "aducanumab" in asset_lower:
                return ["amyloid", "amyloid-beta", "Aβ", "beta-amyloid", "amyloid precursor protein", "APP"]
            elif "lecanemab" in asset_lower:
                return ["amyloid", "amyloid-beta", "Aβ", "beta-amyloid", "amyloid precursor protein", "APP"]
            else:
                return []
    
    def _normalize_term(self, term: str) -> str:
        """Normalize a term for deduplication (casefold + ASCII normalize)."""
        if not term:
            return ""
        # Unicode normalization (NFC) + casefold + strip
        normalized = unicodedata.normalize('NFC', term.strip().lower())
        return normalized
    
    def _deduplicate_and_normalize(self, terms: List[str]) -> List[str]:
        """Deduplicate and normalize terms."""
        if not self.enable_deduplication:
            return terms
        
        seen: Set[str] = set()
        result: List[str] = []
        
        for term in terms:
            if not term:
                continue
            
            if self.enable_normalization:
                normalized = self._normalize_term(term)
            else:
                normalized = term.strip().lower()
            
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(term.strip())
        
        return result
    
    def _limit_tier_c_terms(self, terms: List[str]) -> List[str]:
        """Limit the number of tier C terms to prevent query explosion."""
        if len(terms) <= self.max_tier_c_terms:
            return terms
        
        # Keep the first N terms (could be improved with ranking)
        limited = terms[:self.max_tier_c_terms]
        self.logger.info(f"Limited mechanism targets from {len(terms)} to {len(limited)} terms")
        return limited
    
    def update_entity_pack_with_nct_ids(self, entity_pack: EntityPack, nct_ids: List[str]) -> EntityPack:
        """Update entity pack with discovered NCT IDs."""
        if not nct_ids:
            return entity_pack
        
        # Merge with existing NCT IDs
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
        
        self.logger.info(f"Updated entity pack {entity_pack.entity_id} with {len(nct_ids)} new NCT IDs")
        return updated_pack
