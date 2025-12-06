"""
VAERS processor for extracting vaccine adverse event data.

Extracts:
- Drug entities (vaccines with adverse events)
- Disease entities (adverse events/conditions)
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


class VAERSProcessor(BaseProcessor):
    """
    Processor for VAERS (Vaccine Adverse Event Reporting System) data.
    
    VAERS provides:
    - Vaccine names (drugs with reported adverse events)
    - Adverse event terms (diseases/conditions)
    - Event dates
    """
    
    SOURCE_NAME = "vaers"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from VAERS data."""
        return raw_data.get('vaers_id') or raw_data.get('report_id') or raw_data.get('id', '')
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from VAERS record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'drugs': [],
            'diseases': []
        }
        
        try:
            drugs = self._extract_vaccines(raw_data)
            entities['drugs'].extend(drugs)
            self.metrics.entities_extracted += len(drugs)
            
            diseases = self._extract_adverse_events(raw_data)
            entities['diseases'].extend(diseases)
            self.metrics.entities_extracted += len(diseases)
            
        except Exception as e:
            logger.error(f"Error extracting VAERS data: {e}")
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
        
        disease_ids = resolved_entities.get('diseases', [])
        if isinstance(disease_ids, UUID):
            disease_ids = [disease_ids]
        elif not isinstance(disease_ids, list):
            disease_ids = []
        
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
                        attributes={'source': 'vaers'},
                        temporal={}
                    ))
        
        return relationships
    
    def _extract_vaccines(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract vaccine entities from VAERS data."""
        vaccines = []
        
        vaccine_names = raw_data.get('vaccine_name', [])
        if isinstance(vaccine_names, str):
            vaccine_names = [vaccine_names]
        elif not isinstance(vaccine_names, list):
            vaccine_names = []
        
        for vaccine_name in vaccine_names:
            if vaccine_name and len(vaccine_name) > 2:
                drug = ExtractedEntity(
                    entity_type=EntityType.DRUG,
                    name=self.normalize_drug_name(vaccine_name),
                    identifiers={},
                    context={'is_vaccine': True, 'has_adverse_events': True, 'source': 'vaers'},
                    source_name=self.SOURCE_NAME,
                    source_identifier=self.get_source_identifier(raw_data),
                    raw_data={'vaccine_name': vaccine_name}
                )
                vaccines.append(drug)
        
        return vaccines
    
    def _extract_adverse_events(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract disease entities (adverse events)."""
        diseases = []
        
        adverse_events = raw_data.get('symptom') or raw_data.get('adverse_event', [])
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
                    context={'is_adverse_event': True, 'source': 'vaers'},
                    source_name=self.SOURCE_NAME,
                    source_identifier=self.get_source_identifier(raw_data),
                    raw_data={'adverse_event': event}
                )
                diseases.append(disease)
        
        return diseases
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        return bool(entities.get('drugs') or entities.get('diseases'))
