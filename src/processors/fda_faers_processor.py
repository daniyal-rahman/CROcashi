"""
FDA FAERS processor for extracting adverse event data.

Extracts:
- Drug entities (drugs with adverse events)
- Company entities (manufacturers)
- Disease entities (adverse events/indications)
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


class FDAFAERSProcessor(BaseProcessor):
    """
    Processor for FDA FAERS (Adverse Event Reporting System) data.
    
    FAERS provides:
    - Drug names (drugs with reported adverse events)
    - Company information (manufacturers)
    - Adverse event terms (diseases/conditions)
    - Event dates
    """
    
    SOURCE_NAME = "fda_faers"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from FAERS data."""
        return raw_data.get('case_id') or raw_data.get('report_id') or raw_data.get('id', '')
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from FAERS record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'drugs': [],
            'companies': [],
            'diseases': []
        }
        
        try:
            drugs = self._extract_drugs(raw_data)
            entities['drugs'].extend(drugs)
            self.metrics.entities_extracted += len(drugs)
            
            companies = self._extract_companies(raw_data)
            entities['companies'].extend(companies)
            self.metrics.entities_extracted += len(companies)
            
            diseases = self._extract_adverse_events(raw_data)
            entities['diseases'].extend(diseases)
            self.metrics.entities_extracted += len(diseases)
            
        except Exception as e:
            logger.error(f"Error extracting FAERS data: {e}")
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
        
        drug_ids = resolved_entities.get('drugs', [])
        if isinstance(drug_ids, UUID):
            drug_ids = [drug_ids]
        elif not isinstance(drug_ids, list):
            drug_ids = []
        
        company_ids = resolved_entities.get('companies', [])
        if isinstance(company_ids, UUID):
            company_ids = [company_ids]
        elif not isinstance(company_ids, list):
            company_ids = []
        
        disease_ids = resolved_entities.get('diseases', [])
        if isinstance(disease_ids, UUID):
            disease_ids = [disease_ids]
        elif not isinstance(disease_ids, list):
            disease_ids = []
        
        # Drug-company relationships
        for drug_id in drug_ids:
            drug_entity = id_to_entity.get(drug_id)
            if not drug_entity:
                continue
            
            for company_id in company_ids:
                company_entity = id_to_entity.get(company_id)
                if company_entity:
                    relationships.append(RelationshipExtraction(
                        relationship_type='company_drug',
                        source_entity=company_entity,
                        target_entity=drug_entity,
                        attributes={'role': 'manufacturer'},
                        temporal={}
                    ))
        
        # Drug-adverse event relationships
        for drug_id in drug_ids:
            drug_entity = id_to_entity.get(drug_id)
            if not drug_entity:
                continue
            
            for disease_id in disease_ids:
                disease_entity = id_to_entity.get(disease_id)
                if disease_entity:
                    relationships.append(RelationshipExtraction(
                        relationship_type='drug_adverse_event',
                        source_entity=drug_entity,
                        target_entity=disease_entity,
                        attributes={'source': 'faers'},
                        temporal={}
                    ))
        
        return relationships
    
    def _extract_drugs(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract drug entities from FAERS data."""
        drugs = []
        
        drug_names = raw_data.get('drug_name', [])
        if isinstance(drug_names, str):
            drug_names = [drug_names]
        elif not isinstance(drug_names, list):
            drug_names = []
        
        for drug_name in drug_names:
            if drug_name and len(drug_name) > 2:
                drug = ExtractedEntity(
                    entity_type=EntityType.DRUG,
                    name=self.normalize_drug_name(drug_name),
                    identifiers={},
                    context={'has_adverse_events': True, 'source': 'faers'},
                    source_name=self.SOURCE_NAME,
                    source_identifier=self.get_source_identifier(raw_data),
                    raw_data={'drug_name': drug_name}
                )
                drugs.append(drug)
        
        return drugs
    
    def _extract_companies(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract company entities (manufacturers)."""
        companies = []
        
        company_name = raw_data.get('manufacturer_name') or raw_data.get('company_name', '')
        if company_name:
            company = ExtractedEntity(
                entity_type=EntityType.COMPANY,
                name=self.normalize_company_name(company_name),
                identifiers={},
                context={'role': 'manufacturer', 'source': 'faers'},
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'company_name': company_name}
            )
            companies.append(company)
        
        return companies
    
    def _extract_adverse_events(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract disease entities (adverse events)."""
        diseases = []
        
        adverse_events = raw_data.get('adverse_event', [])
        if isinstance(adverse_events, str):
            adverse_events = [adverse_events]
        elif not isinstance(adverse_events, list):
            adverse_events = []
        
        for event in adverse_events:
            if event and len(event) > 2:
                disease = ExtractedEntity(
                    entity_type=EntityType.DISEASE,
                    name=event,
                    identifiers={},
                    context={'is_adverse_event': True, 'source': 'faers'},
                    source_name=self.SOURCE_NAME,
                    source_identifier=self.get_source_identifier(raw_data),
                    raw_data={'adverse_event': event}
                )
                diseases.append(disease)
        
        return diseases
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        return bool(entities.get('drugs') or entities.get('diseases'))
