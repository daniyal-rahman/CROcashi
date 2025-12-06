"""
Health Canada processor for extracting Canadian regulatory approval data.

Extracts:
- Company entities (marketing authorization holders)
- Drug entities (approved medicines)
- Regulatory events (Health Canada approvals)
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


class HealthCanadaProcessor(BaseProcessor):
    """
    Processor for Health Canada Drug Product Database data.
    
    Similar to FDA Drugs@FDA but for Canadian approvals.
    """
    
    SOURCE_NAME = "health_canada"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from Health Canada data."""
        return raw_data.get('din') or raw_data.get('product_name', '')[:100] or ''
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from Health Canada record."""
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
            logger.error(f"Error extracting Health Canada data: {e}")
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
                    attributes={'role': 'marketing_authorization_holder'},
                    temporal={}
                ))
        
        event_ids = resolved_entities.get('regulatory_events', [])
        if isinstance(event_ids, UUID):
            event_ids = [event_ids]
        elif not isinstance(event_ids, list):
            event_ids = []
        
        for event_id in event_ids:
            event_entity = id_to_entity.get(event_id)
            if not event_entity:
                continue
            
            if company_id:
                company_entity = id_to_entity.get(company_id)
                if company_entity:
                    relationships.append(RelationshipExtraction(
                        relationship_type='regulatory_company_event',
                        source_entity=event_entity,
                        target_entity=company_entity,
                        attributes={},
                        temporal={}
                    ))
            
            if drug_id:
                drug_entity = id_to_entity.get(drug_id)
                if drug_entity:
                    relationships.append(RelationshipExtraction(
                        relationship_type='regulatory_drug_event',
                        source_entity=event_entity,
                        target_entity=drug_entity,
                        attributes={},
                        temporal={}
                    ))
        
        return relationships
    
    def _extract_company(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract company (marketing authorization holder)."""
        company_name = raw_data.get('company_name') or raw_data.get('manufacturer', '')
        
        if not company_name:
            return None
        
        company_name = self.normalize_company_name(company_name)
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={'role': 'marketing_authorization_holder', 'regulatory_body': 'Health_Canada'},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'company_name': company_name}
        )
        
        return company
    
    def _extract_drug(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract drug entity."""
        drug_name = raw_data.get('product_name') or raw_data.get('brand_name', '')
        
        if not drug_name:
            return None
        
        drug_name = self.normalize_drug_name(drug_name)
        
        drug = ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=drug_name,
            identifiers={'din': raw_data.get('din')},
            context={'regulatory_body': 'Health_Canada', 'approval_date': raw_data.get('approval_date')},
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
        
        drug_name = raw_data.get('product_name', '')
        event_name = f"Health Canada Approval: {drug_name}" if drug_name else "Health Canada Approval"
        
        event = ExtractedEntity(
            entity_type=EntityType.REGULATORY_EVENT,
            name=event_name,
            identifiers={},
            context={
                'event_type': 'approval',
                'event_date': approval_date,
                'regulatory_body': 'Health_Canada',
                'country': 'CA'
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data=raw_data
        )
        
        return event
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        return bool(entities.get('drugs') or entities.get('regulatory_events'))
