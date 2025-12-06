"""
MFDS Korea processor for extracting South Korean regulatory data.

Extracts:
- Company entities (drug manufacturers)
- Drug entities (approved products)
- Regulatory events (approvals)
"""
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)

logger = logging.getLogger(__name__)


class MfdsKoreaProcessor(BaseProcessor):
    """
    Processor for MFDS (South Korea) regulatory data.
    
    MFDS provides:
    - Drug product information
    - Company information (manufacturers)
    - Regulatory events (approvals)
    """
    
    SOURCE_NAME = "mfds_korea"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from MFDS data."""
        return raw_data.get('registration_number') or raw_data.get('product_id') or raw_data.get('url', '')[:100] or ''
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from MFDS record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'companies': [],
            'drugs': [],
            'regulatory_events': []
        }
        
        try:
            company = self._extract_company(raw_data)
            if company:
                entities['companies'].append(company)
                self.metrics.entities_extracted += 1
            
            drug = self._extract_drug(raw_data)
            if drug:
                entities['drugs'].append(drug)
                self.metrics.entities_extracted += 1
            
            event = self._extract_regulatory_event(raw_data)
            if event:
                entities['regulatory_events'].append(event)
                self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting MFDS data: {e}")
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
        relationships = []
        
        company_id = resolved_entities.get('company')
        if not company_id:
            companies = resolved_entities.get('companies', [])
            if isinstance(companies, list) and len(companies) > 0:
                company_id = companies[0]
            elif isinstance(companies, UUID):
                company_id = companies
        
        drug_id = resolved_entities.get('drug')
        if not drug_id:
            drugs = resolved_entities.get('drugs', [])
            if isinstance(drugs, list) and len(drugs) > 0:
                drug_id = drugs[0]
            elif isinstance(drugs, UUID):
                drug_id = drugs
        
        if company_id and drug_id:
            company_entity = id_to_entity.get(company_id)
            drug_entity = id_to_entity.get(drug_id)
            if company_entity and drug_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='company_drug',
                    source_entity=company_entity,
                    target_entity=drug_entity,
                    attributes={'role': 'manufacturer', 'country': 'South Korea'},
                    temporal={}
                ))
        
        return relationships
    
    def _extract_company(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract company entity."""
        company_name = raw_data.get('manufacturer') or raw_data.get('company_name', '')
        if not company_name:
            return None
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=self.normalize_company_name(company_name),
            identifiers={},
            context={'role': 'manufacturer', 'country': 'South Korea'},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'company_name': company_name}
        )
        
        return company
    
    def _extract_drug(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract drug entity."""
        drug_name = raw_data.get('product_name') or raw_data.get('drug_name', '')
        if not drug_name:
            return None
        
        drug = ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=self.normalize_drug_name(drug_name),
            identifiers={},
            context={'country': 'South Korea', 'regulatory_body': 'MFDS'},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'drug_name': drug_name}
        )
        
        return drug
    
    def _extract_regulatory_event(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract regulatory event (approval)."""
        approval_date_dt = self.extract_date_from_raw(raw_data, 'approval_date')
        approval_date = approval_date_dt.date() if approval_date_dt and hasattr(approval_date_dt, 'date') else (approval_date_dt if isinstance(approval_date_dt, date) else None)
        
        if not approval_date:
            approval_date = datetime.now().date()
        
        product_name = raw_data.get('product_name', '')
        event_name = f"MFDS Approval: {product_name[:100]}" if product_name else "MFDS Approval"
        
        event = ExtractedEntity(
            entity_type=EntityType.REGULATORY_EVENT,
            name=event_name,
            identifiers={},
            context={
                'event_type': 'approval',
                'event_date': approval_date,
                'regulatory_body': 'MFDS',
                'country': 'South Korea'
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data=raw_data
        )
        
        return event
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        return bool(entities.get('drugs') or entities.get('regulatory_events'))
