"""
FDA Drugs@FDA processor for extracting drug approval data.

Extracts:
- Drug entity (brand name, generic name, active ingredient)
- Company entity (applicant holder)
- Regulatory events (approval date, application number)
- Drug indications
"""
import logging
from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from src.entity_resolution.base_processor import BaseProcessor
from src.entity_resolution.types import (
    EntityType, ExtractedEntity, RelationshipExtraction
)

logger = logging.getLogger(__name__)


class FDADrugsProcessor(BaseProcessor):
    """
    Processor for FDA Drugs@FDA data.
    
    FDA data provides:
    - Unique application numbers (NDA/BLA)
    - Brand and generic drug names
    - Applicant holder (company)
    - Approval dates and types
    - Indications
    """
    
    SOURCE_NAME = "fda_drugs"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get application number from FDA data."""
        return raw_data.get('application_number', raw_data.get('ApplNo', ''))
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from FDA drug approval record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'drugs': [],
            'companies': [],
            'diseases': [],
            'regulatory_events': []
        }
        
        try:
            # Extract drug entity
            drug = self._extract_drug(raw_data)
            if drug:
                entities['drugs'].append(drug)
                self.metrics.entities_extracted += 1
            
            # Extract company (applicant holder)
            company = self._extract_company(raw_data)
            if company:
                entities['companies'].append(company)
                self.metrics.entities_extracted += 1
            
            # Extract indication diseases
            diseases = self._extract_indications(raw_data)
            entities['diseases'].extend(diseases)
            self.metrics.entities_extracted += len(diseases)
            
            # Extract regulatory event
            event = self._extract_regulatory_event(raw_data)
            if event:
                entities['regulatory_events'].append(event)
                self.metrics.entities_extracted += 1
            
        except Exception as e:
            logger.error(f"Error extracting FDA drug data: {e}")
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
        
        drug_id = resolved_entities.get('drug')
        company_id = resolved_entities.get('company')
        event_id = resolved_entities.get('regulatory_event')
        
        # Company-drug relationship (ownership via NDA/BLA holder)
        if drug_id and company_id:
            drug_entity = id_to_entity.get(drug_id)
            company_entity = id_to_entity.get(company_id)
            if drug_entity and company_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='company_drug',
                    source_entity=company_entity,
                    target_entity=drug_entity,
                    attributes={
                        'relationship_type': 'originator',
                        'development_stage': 'approved'
                    },
                    temporal={
                        'start_date': self.extract_date_from_raw(raw_data, 'approval_date')
                    }
                ))
        
        # Regulatory event - drug relationship
        if event_id and drug_id:
            event_entity = id_to_entity.get(event_id)
            drug_entity = id_to_entity.get(drug_id)
            if event_entity and drug_entity:
                disease_ids = resolved_entities.get('diseases', [])
                disease_id = disease_ids[0] if disease_ids else None
                
                relationships.append(RelationshipExtraction(
                    relationship_type='regulatory_drug_event',
                    source_entity=event_entity,
                    target_entity=drug_entity,
                    attributes={
                        'disease_id': disease_id
                    },
                    temporal={}
                ))
        
        # Regulatory event - company relationship
        if event_id and company_id:
            event_entity = id_to_entity.get(event_id)
            company_entity = id_to_entity.get(company_id)
            if event_entity and company_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='regulatory_company_event',
                    source_entity=event_entity,
                    target_entity=company_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Drug indications
        drug_entity = id_to_entity.get(drug_id) if drug_id else None
        if drug_entity:
            for disease_id in resolved_entities.get('diseases', []):
                disease_entity = id_to_entity.get(disease_id)
                if disease_entity:
                    relationships.append(RelationshipExtraction(
                        relationship_type='drug_indication',
                        source_entity=drug_entity,
                        target_entity=disease_entity,
                        attributes={
                            'approved': True,
                            'approval_date': self.extract_date_from_raw(raw_data, 'approval_date')
                        },
                        temporal={}
                    ))
        
        return relationships
    
    def _extract_drug(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Extract drug entity from FDA data."""
        brand_name = raw_data.get('brand_name', raw_data.get('TradeName', ''))
        generic_name = raw_data.get('generic_name', raw_data.get('ActiveIngredient', ''))
        
        # Use brand name as primary if available
        primary_name = brand_name if brand_name else generic_name
        
        if not primary_name:
            return None
        
        # Normalize names
        primary_name = self.normalize_drug_name(primary_name)
        if generic_name:
            generic_name = self.normalize_drug_name(generic_name)
        
        drug = ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=primary_name,
            identifiers={
                'fda_application': self.get_source_identifier(raw_data)
            },
            context={
                'brand_name': brand_name,
                'generic_name': generic_name,
                'approval_date': self.extract_date_from_raw(raw_data, 'approval_date'),
                'application_type': raw_data.get('application_type', '')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data=raw_data
        )
        
        return drug
    
    def _extract_company(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Extract company (applicant holder) from FDA data."""
        company_name = raw_data.get('sponsor_name', 
                                     raw_data.get('SponsorName',
                                                  raw_data.get('applicant', '')))
        
        if not company_name:
            return None
        
        # Normalize company name
        company_name = self.normalize_company_name(company_name)
        
        company = ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={
                'role': 'applicant_holder',
                'fda_application': self.get_source_identifier(raw_data)
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data={'company_name': company_name}
        )
        
        return company
    
    def _extract_indications(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract indication diseases from FDA data."""
        diseases = []
        
        # Try various fields for indications
        indications = raw_data.get('indications', 
                                    raw_data.get('Indication',
                                                 raw_data.get('indication', [])))
        
        if isinstance(indications, str):
            indications = [indications]
        
        for indication in indications:
            if not indication or not isinstance(indication, str):
                continue
            
            indication = indication.strip()
            
            disease = ExtractedEntity(
                entity_type=EntityType.DISEASE,
                name=indication,
                identifiers={},
                context={
                    'source_term': indication,
                    'fda_approved': True
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'indication': indication}
            )
            
            diseases.append(disease)
        
        return diseases
    
    def _extract_regulatory_event(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Extract regulatory event (approval) from FDA data."""
        approval_date = self.extract_date_from_raw(raw_data, 'approval_date')
        application_number = self.get_source_identifier(raw_data)
        
        if not application_number:
            return None
        
        # Determine approval type
        approval_type = raw_data.get('approval_type', '')
        if not approval_type:
            # Infer from application type
            app_type = raw_data.get('application_type', '').lower()
            if 'priority' in app_type:
                approval_type = 'priority_review'
            elif 'accelerated' in app_type:
                approval_type = 'accelerated'
            else:
                approval_type = 'full'
        
        event = ExtractedEntity(
            entity_type=EntityType.REGULATORY_EVENT,
            name=f"FDA Approval {application_number}",
            identifiers={
                'application_number': application_number
            },
            context={
                'event_type': 'approval',
                'event_date': approval_date,
                'regulatory_body': 'FDA',
                'approval_type': approval_type,
                'country': 'US'
            },
            source_name=self.SOURCE_NAME,
            source_identifier=application_number,
            raw_data=raw_data
        )
        
        return event
    
    def _make_drug_entity(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Helper to create drug entity stub."""
        brand_name = raw_data.get('brand_name', raw_data.get('TradeName', ''))
        # CRITICAL: Normalize to match original extraction (for stub key matching)
        if brand_name:
            brand_name = self.normalize_drug_name(brand_name)
        return ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=brand_name,
            identifiers={},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )
    
    def _make_company_entity(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Helper to create company entity stub."""
        company_name = raw_data.get('sponsor_name', raw_data.get('SponsorName', ''))
        # CRITICAL: Normalize to match original extraction (for stub key matching)
        if company_name:
            company_name = self.normalize_company_name(company_name)
        return ExtractedEntity(
            entity_type=EntityType.COMPANY,
            name=company_name,
            identifiers={},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )
    
    def _make_regulatory_event_entity(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Helper to create regulatory event entity stub."""
        return ExtractedEntity(
            entity_type=EntityType.REGULATORY_EVENT,
            name=f"FDA Approval {self.get_source_identifier(raw_data)}",
            identifiers={'application_number': self.get_source_identifier(raw_data)},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )
    
    def _make_indication_entity(self, raw_data: Dict[str, Any], index: int) -> ExtractedEntity:
        """Helper to create indication entity stub."""
        indications = raw_data.get('indications', [])
        if isinstance(indications, str):
            indications = [indications]
        
        indication_name = indications[index] if index < len(indications) else ''
        # Note: Disease names typically don't need normalization, but keep for consistency
        if indication_name:
            indication_name = indication_name.strip()
        
        return ExtractedEntity(
            entity_type=EntityType.DISEASE,
            name=indication_name,
            identifiers={},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )

