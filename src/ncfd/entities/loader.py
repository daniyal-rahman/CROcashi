"""
Entity pack loader for loading and managing entity packs from YAML files.
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional
from .schema import EntityPack, CompanyInfo, AssetInfo, MechanismInfo, IndicationInfo, RegistryInfo, PublisherInfo, AuthorInfo, DateRangeInfo

logger = logging.getLogger(__name__)


class EntityPackLoader:
    """Loads and manages entity packs from YAML files."""
    
    def __init__(self, packs_dir: str = "config/entity_packs"):
        """
        Initialize entity pack loader.
        
        Args:
            packs_dir: Directory containing entity pack YAML files
        """
        self.packs_dir = Path(packs_dir)
        self._cache: Dict[str, EntityPack] = {}
        self._ensure_packs_dir()
    
    def _ensure_packs_dir(self):
        """Ensure the packs directory exists."""
        self.packs_dir.mkdir(parents=True, exist_ok=True)
    
    def load_pack(self, entity_id: str, use_cache: bool = True) -> EntityPack:
        """
        Load a specific entity pack by ID.
        
        Args:
            entity_id: The entity ID to load
            use_cache: Whether to use cached version if available
            
        Returns:
            Loaded entity pack
            
        Raises:
            FileNotFoundError: If entity pack file doesn't exist
            ValueError: If entity pack data is invalid
        """
        if use_cache and entity_id in self._cache:
            return self._cache[entity_id]
        
        pack_file = self.packs_dir / f"{entity_id}.yaml"
        if not pack_file.exists():
            raise FileNotFoundError(f"Entity pack file not found: {pack_file}")
        
        try:
            with open(pack_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # Validate required fields
            self._validate_entity_data(data)
            
            # Build entity pack
            pack = self._build_entity_pack(data)
            
            # Cache if requested
            if use_cache:
                self._cache[entity_id] = pack
            
            logger.info(f"Loaded entity pack: {entity_id}")
            return pack
            
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in entity pack {entity_id}: {e}")
        except Exception as e:
            raise ValueError(f"Error loading entity pack {entity_id}: {e}")
    
    def load_all_packs(self, use_cache: bool = True) -> Dict[str, EntityPack]:
        """
        Load all entity packs from the packs directory.
        
        Args:
            use_cache: Whether to use cached versions if available
            
        Returns:
            Dictionary mapping entity IDs to entity packs
        """
        packs = {}
        
        for pack_file in self.packs_dir.glob("*.yaml"):
            entity_id = pack_file.stem
            try:
                packs[entity_id] = self.load_pack(entity_id, use_cache)
            except Exception as e:
                logger.warning(f"Failed to load entity pack {entity_id}: {e}")
                continue
        
        logger.info(f"Loaded {len(packs)} entity packs")
        return packs
    
    def reload_pack(self, entity_id: str) -> EntityPack:
        """
        Reload an entity pack, bypassing cache.
        
        Args:
            entity_id: The entity ID to reload
            
        Returns:
            Reloaded entity pack
        """
        if entity_id in self._cache:
            del self._cache[entity_id]
        return self.load_pack(entity_id, use_cache=False)
    
    def clear_cache(self):
        """Clear the entity pack cache."""
        self._cache.clear()
        logger.info("Entity pack cache cleared")
    
    def list_available_packs(self) -> List[str]:
        """
        List all available entity pack IDs.
        
        Returns:
            List of entity IDs
        """
        return [f.stem for f in self.packs_dir.glob("*.yaml")]
    
    def _validate_entity_data(self, data: Dict) -> None:
        """Validate entity pack data structure."""
        required_fields = [
            'entity_id', 'company', 'asset', 'mechanism', 
            'indications', 'registries', 'publishers', 'date_ranges'
        ]
        
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate company structure
        company = data['company']
        if 'canonical' not in company or 'aliases' not in company:
            raise ValueError("Company must have 'canonical' and 'aliases' fields")
        
        # Validate asset structure
        asset = data['asset']
        if 'canonical' not in asset or 'aliases' not in asset:
            raise ValueError("Asset must have 'canonical' and 'aliases' fields")
        
        # Validate mechanism structure
        mechanism = data['mechanism']
        if 'targets' not in mechanism:
            raise ValueError("Mechanism must have 'targets' field")
        
        # Validate indications structure
        indications = data['indications']
        if 'primary' not in indications or 'synonyms' not in indications:
            raise ValueError("Indications must have 'primary' and 'synonyms' fields")
        
        # Validate registries structure
        registries = data['registries']
        if 'nct_ids' not in registries:
            raise ValueError("Registries must have 'nct_ids' field")
    
    def _build_entity_pack(self, data: Dict) -> EntityPack:
        """Build EntityPack from validated data."""
        return EntityPack(
            entity_id=data['entity_id'],
            company=CompanyInfo(
                canonical=data['company']['canonical'],
                aliases=data['company']['aliases']
            ),
            asset=AssetInfo(
                canonical=data['asset']['canonical'],
                aliases=data['asset']['aliases']
            ),
            mechanism=MechanismInfo(
                targets=data['mechanism']['targets']
            ),
            indications=IndicationInfo(
                primary=data['indications']['primary'],
                synonyms=data['indications']['synonyms']
            ),
            registries=RegistryInfo(
                nct_ids=data['registries']['nct_ids'],
                cas_rn=data['registries'].get('cas_rn'),
                uspto_ids=data['registries'].get('uspto_ids', [])
            ),
            publishers=PublisherInfo(
                sponsor_strings=data['publishers']['sponsor_strings']
            ),
            date_ranges=DateRangeInfo(
                active_since=data['date_ranges']['active_since'],
                active_until=data['date_ranges'].get('active_until')
            ),
            authors=AuthorInfo(
                primary=data['authors']['primary'],
                aliases=data['authors']['aliases']
            ) if 'authors' in data else None,
            notes=data.get('notes')
        )
