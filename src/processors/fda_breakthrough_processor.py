"""
FDA Breakthrough Therapy Designation processor.

Extracts:
- Company entities (sponsor companies)
- Drug entities (drugs with breakthrough designation)
- Regulatory events (breakthrough designations)
"""
import logging
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)

logger = logging.getLogger(__name__)


class FDABreakthroughProcessor(BaseProcessor):
    """
    Processor for FDA Breakthrough Therapy Designation data.
    
    FDA Breakthrough Designations provide:
    - Company information (sponsor)
    - Drug names (drugs with breakthrough designation)
    - Designation dates
    - Regulatory event (breakthrough designation)
    """
    
    SOURCE_NAME = "fda_breakthrough"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from FDA breakthrough designation data."""
        return raw_data.get('url') or raw_data.get('designation_id') or raw_data.get('raw_text', '')[:100] or ''
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from FDA breakthrough designation record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'companies': [],
            'drugs': [],
            'regulatory_events': []
        }
        
        try:
            # Extract company entity
            company = self._extract_company(raw_data)
            if company:
                entities['companies'].append(company)
                self.metrics.entities_extracted += 1
            
            # Extract drug entity
            drug = self._extract_drug(raw_data)
            if drug:
                entities['drugs'].append(drug)
                self.metrics.entities_extracted += 1
            
            # Extract regulatory event (breakthrough designation)
            event = self._extract_regulatory_event(raw_data)
            if event:
                entities['regulatory_events'].append(event)
                self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting FDA breakthrough designation data: {e}")
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
        
        # Get resolved entity IDs
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
        
        event_ids = resolved_entities.get('regulatory_events', [])
        if isinstance(event_ids, UUID):
            event_ids = [event_ids]
        elif not isinstance(event_ids, list):
            event_ids = []
        
        # Company-drug relationship
        if company_id and drug_id:
            company_entity = id_to_entity.get(company_id)
            drug_entity = id_to_entity.get(drug_id)
            if company_entity and drug_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='company_drug',
                    source_entity=company_entity,
                    target_entity=drug_entity,
                    attributes={'role': 'developer'},
                    temporal={}
                ))
        
        # Regulatory event - company relationship
        for event_id in event_ids:
            event_entity = id_to_entity.get(event_id)
            if not event_entity or not company_id:
                continue
            
            company_entity = id_to_entity.get(company_id)
            if company_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='regulatory_company_event',
                    source_entity=event_entity,
                    target_entity=company_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Regulatory event - drug relationship
        for event_id in event_ids:
            event_entity = id_to_entity.get(event_id)
            if not event_entity or not drug_id:
                continue
            
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
        """Extract company (sponsor) from breakthrough designation data."""
        company_name = raw_data.get('company_name', '')
        
        if not company_name:
            raw_text = raw_data.get('raw_text', '')
            if raw_text:
                parts = re.split(r'[-–—:]', raw_text, maxsplit=1)
                if len(parts) > 0:
                    company_name = parts[0].strip()
        
        if not company_name:
            logger.warning("No company name found in FDA breakthrough designation")
            return None
        
        company_name = self.normalize_company_name(company_name)
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={
                'role': 'sponsor',
                'designation_type': 'breakthrough'
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'company_name': company_name}
        )
        
        return company
    
    def _extract_drug(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract drug from breakthrough designation data."""
        drug_name = raw_data.get('drug_name', '')
        
        if not drug_name:
            raw_text = raw_data.get('raw_text', '')
            if raw_text:
                parts = re.split(r'[-–—:]', raw_text, maxsplit=2)
                if len(parts) > 1:
                    drug_name = parts[1].strip()
        
        if not drug_name:
            logger.warning("No drug name found in FDA breakthrough designation")
            return None
        
        drug_name = self.normalize_drug_name(drug_name)
        
        drug = ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=drug_name,
            identifiers={},
            context={
                'breakthrough_designation': True,
                'designation_date': raw_data.get('designation_date')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'drug_name': drug_name}
        )
        
        return drug
    
    def _extract_regulatory_event(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract regulatory event (breakthrough designation) from data."""
        designation_date_dt = self.extract_date_from_raw(raw_data, 'designation_date')
        designation_date = designation_date_dt.date() if designation_date_dt and hasattr(designation_date_dt, 'date') else (designation_date_dt if isinstance(designation_date_dt, date) else None)
        
        if not designation_date:
            logger.warning(f"Could not parse designation_date for breakthrough designation, using current date as fallback")
            designation_date = datetime.now().date()
        
        company_name = raw_data.get('company_name', '')
        drug_name = raw_data.get('drug_name', '')
        
        event_name = f"FDA Breakthrough Designation"
        if company_name and drug_name:
            event_name = f"FDA Breakthrough: {company_name} - {drug_name}"
        elif company_name:
            event_name = f"FDA Breakthrough: {company_name}"
        
        event = ExtractedEntity(
            entity_type=EntityType.REGULATORY_EVENT,
            name=event_name,
            identifiers={},
            context={
                'event_type': 'breakthrough',
                'event_date': designation_date,
                'regulatory_body': 'FDA',
                'country': 'US',
                'description': raw_data.get('additional_info', '')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data=raw_data
        )
        
        return event
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        if not entities.get('regulatory_events'):
            return False
        
        if not entities.get('companies') and not entities.get('drugs'):
            logger.warning("Breakthrough designation missing both company and drug")
        
        return True
