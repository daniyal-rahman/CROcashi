"""
WHO ICTRP processor for extracting global clinical trial data.

Extracts:
- Trial entity (trial ID, phase, status, dates)
- Sponsor companies/institutions
- Interventions → drugs
- Conditions → diseases
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


class WHOICTRPProcessor(BaseProcessor):
    """
    Processor for WHO ICTRP (International Clinical Trials Registry Platform) data.
    
    WHO ICTRP provides:
    - Unique trial identifiers
    - Sponsor information
    - Intervention (drug) names
    - Condition (disease) names
    - Phase, status, and enrollment information
    """
    
    SOURCE_NAME = "who_ictrp"
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """Get unique identifier from WHO ICTRP data."""
        return raw_data.get('trial_id') or raw_data.get('trial_number') or raw_data.get('id', '')
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """Extract entities from WHO ICTRP record."""
        self.metrics.start_time = datetime.now()
        
        entities = {
            'trials': [],
            'companies': [],
            'institutions': [],
            'drugs': [],
            'diseases': []
        }
        
        try:
            trial = self._extract_trial(raw_data)
            if trial:
                entities['trials'].append(trial)
                self.metrics.entities_extracted += 1
            
            sponsors = self._extract_sponsors(raw_data)
            for sponsor in sponsors:
                if sponsor.entity_type == EntityType.COMPANY:
                    entities['companies'].append(sponsor)
                else:
                    entities['institutions'].append(sponsor)
                self.metrics.entities_extracted += 1
            
            drugs = self._extract_drugs(raw_data)
            entities['drugs'].extend(drugs)
            self.metrics.entities_extracted += len(drugs)
            
            diseases = self._extract_diseases(raw_data)
            entities['diseases'].extend(diseases)
            self.metrics.entities_extracted += len(diseases)
            
        except Exception as e:
            logger.error(f"Error extracting WHO ICTRP data: {e}")
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
        
        trial_id = resolved_entities.get('trial')
        if not trial_id:
            trials = resolved_entities.get('trials', [])
            if isinstance(trials, list) and len(trials) > 0:
                trial_id = trials[0]
            elif isinstance(trials, UUID):
                trial_id = trials
        
        if not trial_id:
            return relationships
        
        trial_entity = id_to_entity.get(trial_id)
        if not trial_entity:
            return relationships
        
        # Trial-sponsor relationships
        sponsor_ids = []
        companies = resolved_entities.get('companies', [])
        institutions = resolved_entities.get('institutions', [])
        
        if isinstance(companies, list):
            sponsor_ids.extend(companies)
        elif isinstance(companies, UUID):
            sponsor_ids.append(companies)
        
        if isinstance(institutions, list):
            sponsor_ids.extend(institutions)
        elif isinstance(institutions, UUID):
            sponsor_ids.append(institutions)
        
        for sponsor_id in sponsor_ids:
            sponsor_entity = id_to_entity.get(sponsor_id)
            if sponsor_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='trial_sponsor',
                    source_entity=trial_entity,
                    target_entity=sponsor_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Trial-drug relationships
        drug_ids = resolved_entities.get('drugs', [])
        if isinstance(drug_ids, UUID):
            drug_ids = [drug_ids]
        elif not isinstance(drug_ids, list):
            drug_ids = []
        
        for drug_id in drug_ids:
            drug_entity = id_to_entity.get(drug_id)
            if drug_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='trial_drug',
                    source_entity=trial_entity,
                    target_entity=drug_entity,
                    attributes={},
                    temporal={}
                ))
        
        # Trial-disease relationships
        disease_ids = resolved_entities.get('diseases', [])
        if isinstance(disease_ids, UUID):
            disease_ids = [disease_ids]
        elif not isinstance(disease_ids, list):
            disease_ids = []
        
        for disease_id in disease_ids:
            disease_entity = id_to_entity.get(disease_id)
            if disease_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='trial_disease',
                    source_entity=trial_entity,
                    target_entity=disease_entity,
                    attributes={},
                    temporal={}
                ))
        
        return relationships
    
    def _extract_trial(self, raw_data: Dict[str, Any]) -> Optional[ExtractedEntity]:
        """Extract clinical trial entity."""
        trial_id = self.get_source_identifier(raw_data)
        
        if not trial_id:
            logger.warning("Trial ID missing from WHO ICTRP record")
            return None
        
        phase_str = raw_data.get('phase', '')
        start_date = self.extract_date_from_raw(raw_data, 'start_date')
        status = raw_data.get('status', '').lower()
        
        trial = ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name=raw_data.get('title', raw_data.get('trial_title', '')),
            identifiers={
                'trial_id': trial_id
            },
            context={
                'phase': phase_str,
                'status': status,
                'start_date': start_date,
                'enrollment': raw_data.get('enrollment'),
                'registry': 'WHO ICTRP'
            },
            source_name=self.SOURCE_NAME,
            source_identifier=trial_id,
            raw_data=raw_data
        )
        
        return trial
    
    def _extract_sponsors(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract sponsor entities (companies or institutions)."""
        sponsors = []
        
        sponsor_name = raw_data.get('sponsor') or raw_data.get('sponsor_name', '')
        if sponsor_name:
            # Determine if company or institution
            entity_type = EntityType.COMPANY
            if any(keyword in sponsor_name.lower() for keyword in ['university', 'hospital', 'institute', 'medical center']):
                entity_type = EntityType.INSTITUTION
            
            sponsor = ExtractedEntity(
                entity_type=entity_type,
                name=self.normalize_company_name(sponsor_name) if entity_type == EntityType.COMPANY else sponsor_name,
                identifiers={},
                context={
                    'role': 'sponsor',
                    'registry': 'WHO ICTRP'
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'sponsor_name': sponsor_name}
            )
            sponsors.append(sponsor)
        
        return sponsors
    
    def _extract_drugs(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract drug entities from interventions."""
        drugs = []
        
        interventions = raw_data.get('interventions', [])
        if isinstance(interventions, str):
            interventions = [interventions]
        
        for intervention in interventions:
            if isinstance(intervention, dict):
                drug_name = intervention.get('name') or intervention.get('intervention_name', '')
            else:
                drug_name = str(intervention)
            
            if drug_name and len(drug_name) > 2:
                drug = ExtractedEntity(
                    entity_type=EntityType.DRUG,
                    name=self.normalize_drug_name(drug_name),
                    identifiers={},
                    context={
                        'registry': 'WHO ICTRP'
                    },
                    source_name=self.SOURCE_NAME,
                    source_identifier=self.get_source_identifier(raw_data),
                    raw_data={'drug_name': drug_name}
                )
                drugs.append(drug)
        
        return drugs
    
    def _extract_diseases(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract disease entities from conditions."""
        diseases = []
        
        conditions = raw_data.get('conditions', [])
        if isinstance(conditions, str):
            conditions = [conditions]
        
        for condition in conditions:
            if isinstance(condition, dict):
                disease_name = condition.get('name') or condition.get('condition_name', '')
            else:
                disease_name = str(condition)
            
            if disease_name and len(disease_name) > 2:
                disease = ExtractedEntity(
                    entity_type=EntityType.DISEASE,
                    name=disease_name,
                    identifiers={},
                    context={
                        'registry': 'WHO ICTRP'
                    },
                    source_name=self.SOURCE_NAME,
                    source_identifier=self.get_source_identifier(raw_data),
                    raw_data={'disease_name': disease_name}
                )
                diseases.append(disease)
        
        return diseases
    
    def validate_extraction(self, entities: Dict[str, List[ExtractedEntity]]) -> bool:
        """Validate that extraction produced expected entities."""
        return bool(entities.get('trials'))
