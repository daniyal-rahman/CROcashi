"""
NIH RePORTER processor for extracting research grant data.

Extracts:
- Company entities (grant recipients)
- Institution entities (research institutions)
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)

logger = logging.getLogger(__name__)


class NIHReporterProcessor(BaseProcessor):
    """
    Processor for NIH RePORTER (research grants) data.
    
    NIH RePORTER provides:
    - Grant recipient information (companies/institutions)
    - Grant amounts and dates
    - Research project information
    """
    
    SOURCE_NAME = "nih_reporter"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from NIH RePORTER data."""
        return raw_data.get('project_number') or raw_data.get('application_id') or raw_data.get('id', '')
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from NIH RePORTER record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'companies': [],
            'institutions': []
        }
        
        try:
            # Extract organization (could be company or institution)
            org_name = raw_data.get('organization_name') or raw_data.get('org_name', '')
            if org_name:
                # Try to determine if it's a company or institution
                # For now, treat biotech/pharma companies as companies, others as institutions
                org_lower = org_name.lower()
                if any(term in org_lower for term in ['inc', 'llc', 'corp', 'pharma', 'biotech', 'therapeutics', 'bio']):
                    company = self._extract_company(raw_data)
                    if company:
                        entities['companies'].append(company)
                        self.metrics.entities_extracted += 1
                else:
                    institution = self._extract_institution(raw_data)
                    if institution:
                        entities['institutions'].append(institution)
                        self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting NIH RePORTER data: {e}")
            self.add_error(f"Extraction error: {e}")
        
        self.metrics.end_time = datetime.now()
        return entities
    
    def extract_relationships(
        self,
        raw_data: Dict[str, Any],
        resolved_entities: Dict[str, UUID],
        id_to_entity: Dict[UUID, ExtractedEntity]
    ) -> List[RelationshipExtraction]:
        """Extract relationships after entities are resolved."""
        # NIH grants don't typically create entity relationships
        return []
    
    def _extract_company(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract company entity."""
        org_name = raw_data.get('organization_name') or raw_data.get('org_name', '')
        if not org_name:
            return None
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=self.normalize_company_name(org_name),
            identifiers={},
            context={'role': 'grant_recipient', 'source': 'nih_reporter'},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'organization_name': org_name}
        )
        
        return company
    
    def _extract_institution(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract institution entity."""
        org_name = raw_data.get('organization_name') or raw_data.get('org_name', '')
        if not org_name:
            return None
        
        institution = ExtractedEntity(
            entity_type=EntityType.INSTITUTION,
            name=org_name,
            identifiers={},
            context={'role': 'grant_recipient', 'source': 'nih_reporter'},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'organization_name': org_name}
        )
        
        return institution
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        return bool(entities.get('companies') or entities.get('institutions'))
