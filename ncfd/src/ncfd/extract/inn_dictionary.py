"""
INN/Generic Dictionary Management System

This module implements the dictionary management system for Section 5,
including ChEMBL and WHO INN list integration, asset discovery, and
alias normalization mapping.
"""

import re
import logging
import json
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
from sqlalchemy.orm import Session

from ncfd.db.models import Asset, AssetAlias
from ncfd.extract.asset_extractor import norm_drug_name

logger = logging.getLogger(__name__)


@dataclass
class DictionaryEntry:
    """Represents a drug name dictionary entry."""
    alias_text: str
    alias_norm: str
    alias_type: str  # 'inn', 'generic', 'chembl', 'unii', 'drugbank'
    source: str      # 'chembl', 'who_inn', 'manual', etc.
    confidence: float = 1.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class AssetDiscovery:
    """Represents a discovered asset from text extraction."""
    value_text: str
    value_norm: str
    alias_type: str
    source: str
    confidence: float
    existing_asset_id: Optional[int] = None
    needs_asset_creation: bool = False


class INNDictionaryManager:
    """Manages INN/generic dictionaries and asset discovery."""
    
    def __init__(self, db_session: Session):
        """
        Initialize the dictionary manager.
        
        Args:
            db_session: Database session for queries and updates
        """
        self.db_session = db_session
        
        # In-memory dictionary for fast lookups
        self._alias_norm_map: Dict[str, List[DictionaryEntry]] = {}
        self._loaded_sources: Set[str] = set()
        
        # Configuration
        self.confidence_thresholds = {
            'exact_match': 1.0,
            'chembl_approved': 0.95,
            'who_inn_recommended': 0.95,
            'who_inn_proposed': 0.85,
            'generic_name': 0.80,
            'trade_name': 0.70
        }
    
    def load_chembl_dictionary(self, chembl_file_path: str) -> int:
        """
        Load ChEMBL drug names into the dictionary.
        
        Args:
            chembl_file_path: Path to ChEMBL data file (JSON or CSV)
            
        Returns:
            Number of entries loaded
        """
        logger.info(f"Loading ChEMBL dictionary from {chembl_file_path}")
        
        try:
            # For now, simulate ChEMBL data structure
            # In production, this would parse actual ChEMBL dump files
            sample_chembl_data = self._get_sample_chembl_data()
            
            entries_loaded = 0
            for entry_data in sample_chembl_data:
                entry = DictionaryEntry(
                    alias_text=entry_data['name'],
                    alias_norm=norm_drug_name(entry_data['name']),
                    alias_type='chembl',
                    source='chembl',
                    confidence=self.confidence_thresholds['chembl_approved'],
                    metadata={
                        'chembl_id': entry_data.get('chembl_id'),
                        'molecule_type': entry_data.get('molecule_type'),
                        'therapeutic_flag': entry_data.get('therapeutic_flag')
                    }
                )
                
                self._add_to_dictionary(entry)
                entries_loaded += 1
            
            self._loaded_sources.add('chembl')
            logger.info(f"Loaded {entries_loaded} ChEMBL entries")
            return entries_loaded
            
        except Exception as e:
            logger.error(f"Failed to load ChEMBL dictionary: {e}")
            return 0
    
    def load_who_inn_dictionary(self, who_inn_file_path: str) -> int:
        """
        Load WHO INN (International Nonproprietary Names) into dictionary.
        
        Args:
            who_inn_file_path: Path to WHO INN data file
            
        Returns:
            Number of entries loaded
        """
        logger.info(f"Loading WHO INN dictionary from {who_inn_file_path}")
        
        try:
            # For now, simulate WHO INN data structure
            # In production, this would parse WHO INN list files
            sample_inn_data = self._get_sample_who_inn_data()
            
            entries_loaded = 0
            for entry_data in sample_inn_data:
                # Determine confidence based on INN status
                confidence = self.confidence_thresholds['who_inn_recommended']
                if entry_data.get('status') == 'proposed':
                    confidence = self.confidence_thresholds['who_inn_proposed']
                
                entry = DictionaryEntry(
                    alias_text=entry_data['inn'],
                    alias_norm=norm_drug_name(entry_data['inn']),
                    alias_type='inn',
                    source='who_inn',
                    confidence=confidence,
                    metadata={
                        'inn_status': entry_data.get('status'),
                        'therapeutic_class': entry_data.get('therapeutic_class'),
                        'year_proposed': entry_data.get('year_proposed')
                    }
                )
                
                self._add_to_dictionary(entry)
                entries_loaded += 1
            
            self._loaded_sources.add('who_inn')
            logger.info(f"Loaded {entries_loaded} WHO INN entries")
            return entries_loaded
            
        except Exception as e:
            logger.error(f"Failed to load WHO INN dictionary: {e}")
            return 0
    
    def build_alias_norm_map(self) -> Dict[str, List[DictionaryEntry]]:
        """
        Build the complete alias_norm → (type, source) mapping.
        
        Returns:
            Dictionary mapping normalized aliases to list of entries
        """
        logger.info("Building complete alias_norm mapping")
        
        # Load existing aliases from database
        self._load_existing_aliases()
        
        logger.info(f"Built alias_norm map with {len(self._alias_norm_map)} unique normalized aliases")
        return self._alias_norm_map
    
    def discover_assets(self, text: str, page_no: int = 1) -> List[AssetDiscovery]:
        """
        Discover assets in text using dictionary lookup.
        
        Args:
            text: Text to analyze
            page_no: Page number for span tracking
            
        Returns:
            List of discovered assets with confidence scores
        """
        discoveries = []
        
        # Ensure dictionaries are loaded
        if not self._alias_norm_map:
            self.build_alias_norm_map()
        
        # Tokenize text and check each token/phrase
        tokens = self._tokenize_for_drug_names(text)
        
        for token_info in tokens:
            token_norm = norm_drug_name(token_info['text'])
            
            if token_norm in self._alias_norm_map:
                entries = self._alias_norm_map[token_norm]
                
                for entry in entries:
                    # Check if this asset already exists
                    existing_asset = self._find_existing_asset(entry)
                    
                    discovery = AssetDiscovery(
                        value_text=token_info['text'],
                        value_norm=token_norm,
                        alias_type=entry.alias_type,
                        source=entry.source,
                        confidence=entry.confidence,
                        existing_asset_id=existing_asset.asset_id if existing_asset else None,
                        needs_asset_creation=existing_asset is None
                    )
                    
                    discoveries.append(discovery)
        
        return discoveries
    
    def create_asset_shell(self, discovery: AssetDiscovery) -> Asset:
        """
        Create a shell asset row for unknown entities.
        
        Args:
            discovery: AssetDiscovery with entity information
            
        Returns:
            Created Asset instance
        """
        logger.info(f"Creating asset shell for {discovery.value_text}")
        
        # Create asset with minimal information
        asset = Asset(
            names_jsonb={
                'primary_name': discovery.value_text,
                'normalized_name': discovery.value_norm,
                'discovery_source': discovery.source
            }
        )
        
        self.db_session.add(asset)
        self.db_session.flush()  # Get the asset_id
        
        # Create initial alias
        alias = AssetAlias(
            asset_id=asset.asset_id,
            alias_text=discovery.value_text,
            alias_norm=discovery.value_norm,
            alias_type=discovery.alias_type,
            confidence=discovery.confidence
        )
        
        self.db_session.add(alias)
        
        logger.info(f"Created asset {asset.asset_id} with alias {discovery.value_text}")
        return asset
    
    def backfill_asset_ids(self, asset: Asset, external_ids: Dict[str, str]):
        """
        Backfill names_jsonb with external IDs as they become available.
        
        Args:
            asset: Asset to update
            external_ids: Dict of external identifiers (chembl_id, unii, etc.)
        """
        logger.info(f"Backfilling asset {asset.asset_id} with external IDs")
        
        # Update names_jsonb with new identifiers
        current_names = asset.names_jsonb or {}
        
        for id_type, id_value in external_ids.items():
            if id_value:  # Only add non-empty values
                current_names[id_type] = id_value
        
        asset.names_jsonb = current_names
        
        # Create new aliases for external IDs if they're names
        for id_type, id_value in external_ids.items():
            if id_type in ['chembl_id', 'unii', 'drugbank_id']:
                # Check if alias already exists
                existing_alias = self.db_session.query(AssetAlias).filter(
                    AssetAlias.asset_id == asset.asset_id,
                    AssetAlias.alias_norm == norm_drug_name(id_value),
                    AssetAlias.alias_type == id_type.replace('_id', '')
                ).first()
                
                if not existing_alias:
                    alias = AssetAlias(
                        asset_id=asset.asset_id,
                        alias_text=id_value,
                        alias_norm=norm_drug_name(id_value),
                        alias_type=id_type.replace('_id', ''),
                        confidence=self.confidence_thresholds['exact_match']
                    )
                    self.db_session.add(alias)
        
        logger.info(f"Backfilled asset {asset.asset_id} with {len(external_ids)} external IDs")
    
    def _add_to_dictionary(self, entry: DictionaryEntry):
        """Add entry to in-memory dictionary."""
        if entry.alias_norm not in self._alias_norm_map:
            self._alias_norm_map[entry.alias_norm] = []
        
        self._alias_norm_map[entry.alias_norm].append(entry)
    
    def _load_existing_aliases(self):
        """Load existing aliases from database into dictionary."""
        logger.info("Loading existing aliases from database")
        
        aliases = self.db_session.query(AssetAlias).all()
        
        for alias in aliases:
            entry = DictionaryEntry(
                alias_text=alias.alias_text,
                alias_norm=alias.alias_norm,
                alias_type=alias.alias_type,
                source='database',
                confidence=alias.confidence or 1.0,
                metadata={'asset_id': alias.asset_id}
            )
            
            self._add_to_dictionary(entry)
        
        logger.info(f"Loaded {len(aliases)} existing aliases from database")
    
    def _find_existing_asset(self, entry: DictionaryEntry) -> Optional[Asset]:
        """Find existing asset for a dictionary entry."""
        if 'asset_id' in entry.metadata:
            return self.db_session.query(Asset).filter(
                Asset.asset_id == entry.metadata['asset_id']
            ).first()
        
        # Look for asset with matching alias
        alias = self.db_session.query(AssetAlias).filter(
            AssetAlias.alias_norm == entry.alias_norm,
            AssetAlias.alias_type == entry.alias_type
        ).first()
        
        return alias.asset if alias else None
    
    def _tokenize_for_drug_names(self, text: str) -> List[Dict[str, Any]]:
        """
        Tokenize text for drug name extraction.
        
        Returns:
            List of token dictionaries with text and position info
        """
        tokens = []
        
        # Split on word boundaries but preserve drug name patterns
        # This is a simplified version - production would use more sophisticated NLP
        words = re.finditer(r'\b[A-Za-z][A-Za-z0-9\-]*[A-Za-z0-9]\b', text)
        
        for match in words:
            token_info = {
                'text': match.group(),
                'start': match.start(),
                'end': match.end()
            }
            tokens.append(token_info)
        
        # Also look for multi-word drug names (simplified)
        # In production, this would use more sophisticated phrase detection
        bigrams = re.finditer(r'\b[A-Za-z][A-Za-z0-9\-]+ [A-Za-z][A-Za-z0-9\-]+\b', text)
        
        for match in bigrams:
            token_info = {
                'text': match.group(),
                'start': match.start(),
                'end': match.end()
            }
            tokens.append(token_info)
        
        return tokens
    
    def _get_sample_chembl_data(self) -> List[Dict[str, Any]]:
        """Get sample ChEMBL data for demonstration."""
        return [
            {
                'name': 'Aspirin',
                'chembl_id': 'CHEMBL25',
                'molecule_type': 'Small molecule',
                'therapeutic_flag': True
            },
            {
                'name': 'Paracetamol',
                'chembl_id': 'CHEMBL112',
                'molecule_type': 'Small molecule',
                'therapeutic_flag': True
            },
            {
                'name': 'Ibuprofen',
                'chembl_id': 'CHEMBL521',
                'molecule_type': 'Small molecule',
                'therapeutic_flag': True
            },
            {
                'name': 'Metformin',
                'chembl_id': 'CHEMBL1431',
                'molecule_type': 'Small molecule',
                'therapeutic_flag': True
            },
            {
                'name': 'Pembrolizumab',
                'chembl_id': 'CHEMBL3301610',
                'molecule_type': 'Antibody',
                'therapeutic_flag': True
            }
        ]
    
    def _get_sample_who_inn_data(self) -> List[Dict[str, Any]]:
        """Get sample WHO INN data for demonstration."""
        return [
            {
                'inn': 'acetylsalicylic acid',
                'status': 'recommended',
                'therapeutic_class': 'Analgesic',
                'year_proposed': 1960
            },
            {
                'inn': 'paracetamol',
                'status': 'recommended', 
                'therapeutic_class': 'Analgesic',
                'year_proposed': 1963
            },
            {
                'inn': 'ibuprofen',
                'status': 'recommended',
                'therapeutic_class': 'NSAID',
                'year_proposed': 1966
            },
            {
                'inn': 'metformin',
                'status': 'recommended',
                'therapeutic_class': 'Antidiabetic',
                'year_proposed': 1970
            },
            {
                'inn': 'pembrolizumab',
                'status': 'recommended',
                'therapeutic_class': 'Immunotherapy',
                'year_proposed': 2013
            },
            {
                'inn': 'tebentafusp',
                'status': 'proposed',
                'therapeutic_class': 'Immunotherapy',
                'year_proposed': 2023
            }
        ]


class EnhancedSpanCapture:
    """Enhanced span capture system for comprehensive entity extraction."""
    
    def __init__(self, db_session: Session, inn_manager: INNDictionaryManager):
        """
        Initialize the enhanced span capture system.
        
        Args:
            db_session: Database session
            inn_manager: INN dictionary manager for asset lookups
        """
        self.db_session = db_session
        self.inn_manager = inn_manager
    
    def capture_comprehensive_spans(self, text: str, doc_id: int, page_no: int = 1) -> List[Dict[str, Any]]:
        """
        Capture comprehensive entity spans for evidence storage.
        
        Args:
            text: Text to analyze
            doc_id: Document ID
            page_no: Page number
            
        Returns:
            List of span dictionaries with all required fields
        """
        spans = []
        
        # Asset code detection (existing functionality)
        code_spans = self._capture_asset_code_spans(text, page_no)
        spans.extend(code_spans)
        
        # NCT ID detection (existing functionality)
        nct_spans = self._capture_nct_spans(text, page_no)
        spans.extend(nct_spans)
        
        # Dictionary-based drug name detection (new)
        drug_spans = self._capture_drug_name_spans(text, page_no)
        spans.extend(drug_spans)
        
        # Store spans in database
        self._store_spans_in_database(spans, doc_id)
        
        return spans
    
    def _capture_asset_code_spans(self, text: str, page_no: int) -> List[Dict[str, Any]]:
        """Capture asset code spans using regex detection."""
        from ncfd.extract.asset_extractor import extract_asset_codes
        
        spans = []
        asset_matches = extract_asset_codes(text)
        
        for match in asset_matches:
            span = {
                'page_no': page_no,
                'char_start': match.char_start,
                'char_end': match.char_end,
                'value_text': match.value_text,
                'value_norm': match.value_norm,
                'detector': 'regex',
                'ent_type': 'code',
                'confidence': 0.95  # High confidence for regex matches
            }
            spans.append(span)
        
        return spans
    
    def _capture_nct_spans(self, text: str, page_no: int) -> List[Dict[str, Any]]:
        """Capture NCT ID spans using regex detection."""
        from ncfd.extract.asset_extractor import extract_nct_ids
        
        spans = []
        nct_matches = extract_nct_ids(text)
        
        for match in nct_matches:
            span = {
                'page_no': page_no,
                'char_start': match.char_start,
                'char_end': match.char_end,
                'value_text': match.value_text,
                'value_norm': match.value_norm,
                'detector': 'regex',
                'ent_type': 'nct',
                'confidence': 1.0  # Very high confidence for NCT patterns
            }
            spans.append(span)
        
        return spans
    
    def _capture_drug_name_spans(self, text: str, page_no: int) -> List[Dict[str, Any]]:
        """Capture drug name spans using dictionary lookup."""
        spans = []
        
        # Use INN manager to discover assets
        discoveries = self.inn_manager.discover_assets(text, page_no)
        
        for discovery in discoveries:
            # Find the span in the text
            start_pos = text.find(discovery.value_text)
            if start_pos >= 0:
                span = {
                    'page_no': page_no,
                    'char_start': start_pos,
                    'char_end': start_pos + len(discovery.value_text),
                    'value_text': discovery.value_text,
                    'value_norm': discovery.value_norm,
                    'detector': 'dict',
                    'ent_type': discovery.alias_type,
                    'confidence': discovery.confidence
                }
                spans.append(span)
        
        return spans
    
    def _store_spans_in_database(self, spans: List[Dict[str, Any]], doc_id: int):
        """Store captured spans in document_entities table."""
        from ncfd.db.models import DocumentEntity
        
        for span in spans:
            entity = DocumentEntity(
                doc_id=doc_id,
                ent_type=span['ent_type'],
                value_text=span['value_text'],
                value_norm=span['value_norm'],
                page_no=span['page_no'],
                char_start=span['char_start'],
                char_end=span['char_end'],
                detector=span['detector'],
                confidence=span['confidence']
            )
            
            self.db_session.add(entity)
        
        logger.info(f"Stored {len(spans)} entity spans for document {doc_id}")
