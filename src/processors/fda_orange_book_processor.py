"""
FDA Orange Book processor for extracting patent and exclusivity data.

Extracts:
- Company entities (sponsors/applicants)
- Drug entities (approved drugs)
- Patent entities (patent numbers)
- Regulatory events (approvals with patent/exclusivity info)
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


class FDAOrangeBookProcessor(BaseProcessor):
    """
    Processor for FDA Orange Book data.
    
    FDA Orange Book provides:
    - Company information (sponsors/applicants)
    - Drug names (approved drugs)
    - Patent numbers (patent protection)
    - Exclusivity codes (regulatory exclusivity)
    - Approval dates
    """
    
    SOURCE_NAME = "fda_orange_book"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from FDA Orange Book data."""
        app_no = raw_data.get('application_number') or raw_data.get('applno', '')
        patent_no = raw_data.get('patent_number', '')
        
        if app_no and patent_no:
            return f"{app_no}-{patent_no}"
        elif app_no:
            return app_no
        else:
            return raw_data.get('raw_text', '')[:100] or ''
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from FDA Orange Book record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'companies': [],
            'drugs': [],
            'patents': [],
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
            
            # Extract patent entity (if patent number exists)
            patent = self._extract_patent(raw_data)
            if patent:
                entities['patents'].append(patent)
                self.metrics.entities_extracted += 1
            
            # Extract regulatory event (approval with patent/exclusivity)
            event = self._extract_regulatory_event(raw_data)
            if event:
                entities['regulatory_events'].append(event)
                self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting FDA Orange Book data: {e}")
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
        
        patent_id = resolved_entities.get('patent')
        if not patent_id:
            patents = resolved_entities.get('patents', [])
            if isinstance(patents, list) and len(patents) > 0:
                patent_id = patents[0]
            elif isinstance(patents, UUID):
                patent_id = patents
        
        # Company-drug relationship
        if company_id and drug_id:
            company_entity = id_to_entity.get(company_id)
            drug_entity = id_to_entity.get(drug_id)
            if company_entity and drug_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='company_drug',
                    source_entity=company_entity,
                    target_entity=drug_entity,
                    attributes={'role': 'sponsor'},
                    temporal={}
                ))
        
        # Patent-drug relationship
        if patent_id and drug_id:
            patent_entity = id_to_entity.get(patent_id)
            drug_entity = id_to_entity.get(drug_id)
            if patent_entity and drug_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='patent_drug',
                    source_entity=patent_entity,
                    target_entity=drug_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Patent-company relationship
        if patent_id and company_id:
            patent_entity = id_to_entity.get(patent_id)
            company_entity = id_to_entity.get(company_id)
            if patent_entity and company_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='patent_company',
                    source_entity=patent_entity,
                    target_entity=company_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Regulatory event relationships
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
        """Extract company (sponsor/applicant) from Orange Book data."""
        company_name = raw_data.get('sponsor_name') or raw_data.get('applicant', '')
        
        if not company_name:
            logger.warning("No company name found in FDA Orange Book record")
            return None
        
        company_name = self.normalize_company_name(company_name)
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={
                'role': 'sponsor',
                'application_number': raw_data.get('application_number')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'sponsor_name': company_name}
        )
        
        return company
    
    def _extract_drug(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract drug from Orange Book data."""
        drug_name = raw_data.get('brand_name') or raw_data.get('product', '')
        
        if not drug_name:
            drug_name = raw_data.get('generic_name') or raw_data.get('ingredient', '')
        
        if not drug_name:
            logger.warning("No drug name found in FDA Orange Book record")
            return None
        
        drug_name = self.normalize_drug_name(drug_name)
        
        drug = ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=drug_name,
            identifiers={
                'application_number': raw_data.get('application_number')
            },
            context={
                'brand_name': raw_data.get('brand_name'),
                'generic_name': raw_data.get('generic_name'),
                'exclusivity_code': raw_data.get('exclusivity_code')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'drug_name': drug_name}
        )
        
        return drug
    
    def _extract_patent(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract patent from Orange Book data."""
        patent_number = raw_data.get('patent_number') or raw_data.get('patent', '')
        
        if not patent_number:
            return None
        
        patent = ExtractedEntity(
            entity_type=EntityType.PATENT,
            name=f"US Patent {patent_number}",
            identifiers={
                'patent_number': patent_number,
                'patent_office': 'USPTO'
            },
            context={
                'application_number': raw_data.get('application_number'),
                'exclusivity_code': raw_data.get('exclusivity_code')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'patent_number': patent_number}
        )
        
        return patent
    
    def _extract_regulatory_event(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract regulatory event (approval) from Orange Book data."""
        approval_date_dt = self.extract_date_from_raw(raw_data, 'approval_date')
        approval_date = approval_date_dt.date() if approval_date_dt and hasattr(approval_date_dt, 'date') else (approval_date_dt if isinstance(approval_date_dt, date) else None)
        
        if not approval_date:
            logger.warning(f"Could not parse approval_date for Orange Book record, using current date as fallback")
            approval_date = datetime.now().date()
        
        application_number = raw_data.get('application_number', '')
        drug_name = raw_data.get('brand_name') or raw_data.get('product', '')
        
        event_name = f"FDA Approval {application_number}"
        if drug_name:
            event_name = f"FDA Approval: {drug_name} ({application_number})"
        
        event = ExtractedEntity(
            entity_type=EntityType.REGULATORY_EVENT,
            name=event_name,
            identifiers={
                'application_number': application_number
            },
            context={
                'event_type': 'approval',
                'event_date': approval_date,
                'regulatory_body': 'FDA',
                'country': 'US',
                'patent_number': raw_data.get('patent_number'),
                'exclusivity_code': raw_data.get('exclusivity_code')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data=raw_data
        )
        
        return event
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        # At minimum, we should have a drug or company
        if not entities.get('drugs') and not entities.get('companies'):
            return False
        
        return True
