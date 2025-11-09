"""
Base processor interface for source-specific data processing.

All source processors must inherit from this class and implement
the required methods.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from src.entity_resolution.types import (
    ExtractedEntity, ProcessingMetrics, RelationshipExtraction
)


class BaseProcessor(ABC):
    """
    Abstract base class for all source processors.
    
    Each source processor must:
    1. Extract entities from raw data
    2. Validate extracted data
    3. Provide context for entity resolution
    """
    
    # Source name (override in subclass)
    SOURCE_NAME: str = "unknown"
    
    def __init__(self, session: Session):
        """
        Initialize processor.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.metrics = ProcessingMetrics()
    
    @abstractmethod
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """
        Extract entities from raw source data.
        
        Args:
            raw_data: Raw data from the source (typically dict from JSON/XML)
            
        Returns:
            Dict mapping entity type to list of extracted entities
            Example: {
                'companies': [ExtractedEntity(...), ...],
                'drugs': [ExtractedEntity(...), ...],
                'diseases': [ExtractedEntity(...), ...],
            }
        """
        pass
    
    @abstractmethod
    def extract_relationships(
        self,
        raw_data: Dict[str, Any],
        resolved_entities: Dict[str, UUID],
        id_to_entity: Dict[UUID, ExtractedEntity]
    ) -> List[RelationshipExtraction]:
        """
        Extract relationships between entities.
        
        Args:
            raw_data: Raw source data
            resolved_entities: Dict mapping entity keys to resolved UUIDs
            id_to_entity: Dict mapping resolved UUIDs to their extracted entities
            
        Returns:
            List of relationship extractions
        """
        pass
    
    @abstractmethod
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """
        Get unique identifier for this record in the source system.
        
        Args:
            raw_data: Raw source data
            
        Returns:
            Unique identifier (e.g., NCT number, PMID, accession number)
        """
        pass
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """
        Validate extracted entities.
        
        Args:
            entities: Extracted entities
            
        Returns:
            True if validation passes, False otherwise
        """
        # Basic validation: ensure all entities have names
        for entity_type, entity_list in entities.items():
            for entity in entity_list:
                if not entity.name or not entity.name.strip():
                    self.metrics.warnings.append(
                        f"Entity {entity_type} has empty name"
                    )
                    return False
        
        return True
    
    def extract_date_from_raw(self, raw_data: Dict[str, Any], field_name: str) -> Any:
        """
        Helper to extract date from raw data with error handling.
        
        Args:
            raw_data: Raw data dict
            field_name: Name of date field
            
        Returns:
            Parsed datetime or None
        """
        try:
            date_str = raw_data.get(field_name)
            if date_str:
                # Try parsing common date formats
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%m/%d/%Y']:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except ValueError:
                        continue
                
                # Try ISO format
                try:
                    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    pass
            
            return None
        except Exception as e:
            self.metrics.warnings.append(f"Error parsing date {field_name}: {e}")
            return None
    
    def normalize_company_name(self, name: str) -> str:
        """Normalize company name for better matching (instance method wrapper)."""
        return BaseProcessor.normalize_company_name_static(name)
    
    @staticmethod
    def normalize_company_name_static(name: str) -> str:
        """
        Normalize company name for better matching.
        
        Args:
            name: Company name
            
        Returns:
            Normalized name
        """
        import re
        
        # Remove common suffixes for matching
        name = name.strip()
        
        # Remove Inc., LLC, etc. but keep track
        suffixes = [
            'Inc.', 'Inc', 'LLC', 'Ltd.', 'Ltd', 'Corporation', 'Corp.',
            'Corp', 'Limited', 'GmbH', 'AG', 'SA', 'NV', 'PLC'
        ]
        
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:name.rindex(suffix)].strip()
        
        return name
    
    def normalize_drug_name(self, name: str) -> str:
        """Normalize drug name for better matching (instance method wrapper)."""
        return BaseProcessor.normalize_drug_name_static(name)
    
    @staticmethod
    def normalize_drug_name_static(name: str) -> str:
        """
        Normalize drug name for better matching.
        
        Args:
            name: Drug name
            
        Returns:
            Normalized name
        """
        import re
        
        # Remove common formulation indicators
        name = re.sub(r'\s*\([^)]*\)\s*$', '', name)  # Remove trailing parenthetical
        name = re.sub(r'\s+tablet\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+capsule\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+injection\s*$', '', name, flags=re.IGNORECASE)
        
        return name.strip()
    
    def get_metrics(self) -> ProcessingMetrics:
        """
        Get processing metrics.
        
        Returns:
            ProcessingMetrics object
        """
        return self.metrics
    
    def reset_metrics(self):
        """Reset metrics for new processing run."""
        self.metrics = ProcessingMetrics()
    
    def add_warning(self, message: str):
        """Add a warning message."""
        self.metrics.warnings.append(message)
    
    def add_error(self, message: str):
        """Add an error message."""
        self.metrics.errors.append(message)

