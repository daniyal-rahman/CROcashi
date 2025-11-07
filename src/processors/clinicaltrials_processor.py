"""
ClinicalTrials.gov processor for extracting trial data and relationships.

Extracts:
- Trial entity (NCT ID, phase, status, dates)
- Sponsor companies/institutions
- Collaborator companies/institutions
- Interventions → drugs
- Conditions → diseases
- Temporal information
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


class ClinicalTrialsProcessor(BaseProcessor):
    """
    Processor for ClinicalTrials.gov data.
    
    ClinicalTrials.gov provides well-structured data with:
    - Unique NCT IDs for trials
    - Structured sponsor and collaborator information
    - Intervention (drug) names with other names field
    - Condition (disease) names
    - Phase, status, and enrollment information
    """
    
    SOURCE_NAME = "clinicaltrials_gov"
    
    def __init__(self, session: Session):
        """Initialize ClinicalTrials.gov processor."""
        super().__init__(session)
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """
        Get NCT ID from trial data.
        
        Args:
            raw_data: Raw trial data
            
        Returns:
            NCT ID (e.g., "NCT12345678")
        """
        return raw_data.get('nct_id', raw_data.get('NCTId', ''))
    
    def extract_entities(self, raw_data: Dict[str, Any]) -> Dict[str, List[ExtractedEntity]]:
        """
        Extract all entities from a clinical trial record.
        
        Args:
            raw_data: Raw trial data from ClinicalTrials.gov API
            
        Returns:
            Dict of entity lists by type
        """
        self.metrics.start_time = datetime.now()
        
        entities = {
            'trials': [],
            'companies': [],
            'institutions': [],
            'drugs': [],
            'diseases': []
        }
        
        nct_id = self.get_source_identifier(raw_data)
        
        try:
            # Extract trial entity
            trial = self._extract_trial(raw_data)
            if trial:
                entities['trials'].append(trial)
                self.metrics.entities_extracted += 1
            
            # Extract sponsor (lead sponsor)
            sponsor = self._extract_sponsor(raw_data)
            if sponsor:
                if sponsor.entity_type == EntityType.COMPANY:
                    entities['companies'].append(sponsor)
                else:
                    entities['institutions'].append(sponsor)
                self.metrics.entities_extracted += 1
            
            # Extract collaborators
            collaborators = self._extract_collaborators(raw_data)
            for collab in collaborators:
                if collab.entity_type == EntityType.COMPANY:
                    entities['companies'].append(collab)
                else:
                    entities['institutions'].append(collab)
                self.metrics.entities_extracted += 1
            
            # Extract interventions (drugs)
            drugs = self._extract_interventions(raw_data)
            entities['drugs'].extend(drugs)
            self.metrics.entities_extracted += len(drugs)
            
            # Extract conditions (diseases)
            diseases = self._extract_conditions(raw_data)
            entities['diseases'].extend(diseases)
            self.metrics.entities_extracted += len(diseases)
            
        except Exception as e:
            logger.error(f"Error extracting entities from {nct_id}: {e}")
            self.add_error(f"Extraction error: {e}")
        
        self.metrics.end_time = datetime.now()
        return entities
    
    def extract_relationships(
        self,
        raw_data: Dict[str, Any],
        resolved_entities: Dict[str, UUID]
    ) -> List[RelationshipExtraction]:
        """
        Extract relationships after entities are resolved.
        
        Args:
            raw_data: Raw trial data
            resolved_entities: Map of entity keys to resolved UUIDs
            
        Returns:
            List of relationships to create
        """
        relationships = []
        
        trial_id = resolved_entities.get('trial')
        if not trial_id:
            logger.warning("No trial ID found in resolved entities")
            return relationships
        
        # Create trial sponsor relationships
        if 'sponsor' in resolved_entities:
            relationships.append(self._create_sponsor_relationship(
                raw_data,
                trial_id,
                resolved_entities['sponsor'],
                'lead_sponsor'
            ))
        
        # Create collaborator relationships
        for i, collab_id in enumerate(resolved_entities.get('collaborators', [])):
            relationships.append(self._create_sponsor_relationship(
                raw_data,
                trial_id,
                collab_id,
                'collaborator'
            ))
        
        # Create trial-drug relationships
        for i, drug_id in enumerate(resolved_entities.get('drugs', [])):
            relationships.append(RelationshipExtraction(
                relationship_type='trial_drug',
                source_entity=self._make_trial_entity(raw_data),
                target_entity=self._make_drug_entity(raw_data, i),
                attributes={
                    'arm_name': raw_data.get('interventions', [{}])[i].get('arm_group_label', 'experimental')
                }
            ))
        
        # Create trial-disease relationships
        for i, disease_id in enumerate(resolved_entities.get('diseases', [])):
            relationships.append(RelationshipExtraction(
                relationship_type='trial_disease',
                source_entity=self._make_trial_entity(raw_data),
                target_entity=self._make_disease_entity(raw_data, i),
                attributes={}
            ))
        
        return relationships
    
    def _extract_trial(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Extract clinical trial entity."""
        nct_id = self.get_source_identifier(raw_data)
        
        # Parse phase
        phase_str = raw_data.get('phase', '')
        phase_numeric = self._parse_phase(phase_str)
        
        # Parse dates
        start_date = self.extract_date_from_raw(raw_data, 'start_date')
        completion_date = self.extract_date_from_raw(raw_data, 'completion_date')
        
        # Parse status
        status = raw_data.get('overall_status', '').lower()
        
        trial = ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name=raw_data.get('title', raw_data.get('brief_title', '')),
            identifiers={
                'nct_id': nct_id,
                'eudract_number': raw_data.get('eudract_number', '')
            },
            context={
                'phase': phase_str,
                'phase_numeric': phase_numeric,
                'status': status,
                'study_type': raw_data.get('study_type', ''),
                'enrollment': raw_data.get('enrollment', {}).get('value'),
                'start_date': start_date,
                'completion_date': completion_date,
                'why_stopped': raw_data.get('why_stopped', '')
            },
            source_name=self.SOURCE_NAME,
            source_identifier=nct_id,
            raw_data=raw_data
        )
        
        return trial
    
    def _extract_sponsor(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Extract lead sponsor entity."""
        sponsor_data = raw_data.get('sponsor', {})
        lead_sponsor = sponsor_data.get('lead_sponsor', {})
        
        if not lead_sponsor:
            # Try alternative field names
            lead_sponsor = raw_data.get('lead_sponsor', {})
        
        sponsor_name = lead_sponsor.get('agency', lead_sponsor.get('name', ''))
        sponsor_class = lead_sponsor.get('agency_class', '').lower()
        
        if not sponsor_name:
            return None
        
        # Determine if it's a company or institution
        is_industry = sponsor_class in ['industry', 'company']
        
        # Normalize name
        sponsor_name = self.normalize_company_name(sponsor_name) if is_industry else sponsor_name
        
        entity = ExtractedEntity(
            entity_type=EntityType.COMPANY if is_industry else EntityType.INSTITUTION,
            name=sponsor_name,
            identifiers={},
            context={
                'sponsor_class': sponsor_class,
                'role': 'lead_sponsor'
            },
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data),
            raw_data=lead_sponsor
        )
        
        return entity
    
    def _extract_collaborators(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract collaborator entities."""
        collaborators = []
        
        sponsor_data = raw_data.get('sponsor', {})
        collab_list = sponsor_data.get('collaborators', [])
        
        # Try alternative field name
        if not collab_list:
            collab_list = raw_data.get('collaborators', [])
        
        for collab in collab_list:
            collab_name = collab.get('agency', collab.get('name', ''))
            collab_class = collab.get('agency_class', '').lower()
            
            if not collab_name:
                continue
            
            is_industry = collab_class in ['industry', 'company']
            
            # Normalize name
            collab_name = self.normalize_company_name(collab_name) if is_industry else collab_name
            
            entity = ExtractedEntity(
                entity_type=EntityType.COMPANY if is_industry else EntityType.INSTITUTION,
                name=collab_name,
                identifiers={},
                context={
                    'sponsor_class': collab_class,
                    'role': 'collaborator'
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data=collab
            )
            
            collaborators.append(entity)
        
        return collaborators
    
    def _extract_interventions(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract drug interventions."""
        drugs = []
        
        interventions = raw_data.get('interventions', [])
        if not isinstance(interventions, list):
            interventions = [interventions]
        
        for intervention in interventions:
            intervention_type = intervention.get('intervention_type', '').lower()
            
            # Only extract drug and biological interventions
            if intervention_type not in ['drug', 'biological', 'biologic']:
                continue
            
            drug_name = intervention.get('intervention_name', intervention.get('name', ''))
            if not drug_name:
                continue
            
            # Normalize drug name
            drug_name = self.normalize_drug_name(drug_name)
            
            # Extract other names (aliases)
            other_names = intervention.get('other_names', [])
            if isinstance(other_names, str):
                other_names = [other_names]
            
            # Get arm group info for context
            arm_groups = intervention.get('arm_group_label', [])
            if isinstance(arm_groups, str):
                arm_groups = [arm_groups]
            
            drug = ExtractedEntity(
                entity_type=EntityType.DRUG,
                name=drug_name,
                identifiers={},
                context={
                    'intervention_type': intervention_type,
                    'other_names': other_names,
                    'arm_groups': arm_groups,
                    'description': intervention.get('description', '')
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data=intervention
            )
            
            drugs.append(drug)
        
        return drugs
    
    def _extract_conditions(self, raw_data: Dict[str, Any]) -> List[ExtractedEntity]:
        """Extract disease conditions."""
        diseases = []
        
        conditions = raw_data.get('conditions', [])
        if isinstance(conditions, str):
            conditions = [conditions]
        
        for condition in conditions:
            if not condition:
                continue
            
            # Clean up condition name
            condition = condition.strip()
            
            disease = ExtractedEntity(
                entity_type=EntityType.DISEASE,
                name=condition,
                identifiers={},
                context={
                    'source_term': condition,
                    'trial_phase': raw_data.get('phase', '')
                },
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data),
                raw_data={'condition': condition}
            )
            
            diseases.append(disease)
        
        return diseases
    
    def _create_sponsor_relationship(
        self,
        raw_data: Dict[str, Any],
        trial_id: UUID,
        sponsor_id: UUID,
        role: str
    ) -> RelationshipExtraction:
        """Create a trial sponsor relationship."""
        # Determine entity type from context
        sponsor_data = raw_data.get('sponsor', {})
        lead_sponsor = sponsor_data.get('lead_sponsor', {})
        sponsor_class = lead_sponsor.get('agency_class', '').lower()
        
        is_industry = sponsor_class in ['industry', 'company']
        
        return RelationshipExtraction(
            relationship_type='trial_sponsor',
            source_entity=self._make_trial_entity(raw_data),
            target_entity=ExtractedEntity(
                entity_type=EntityType.COMPANY if is_industry else EntityType.INSTITUTION,
                name=lead_sponsor.get('agency', ''),
                identifiers={},
                context={},
                source_name=self.SOURCE_NAME,
                source_identifier=self.get_source_identifier(raw_data)
            ),
            attributes={
                'entity_type': 'company' if is_industry else 'institution',
                'sponsor_role': role,
                'is_regulatory_sponsor': True,
                'is_financial_sponsor': True
            },
            temporal={}
        )
    
    def _make_trial_entity(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Helper to create trial entity stub for relationships."""
        return ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name=raw_data.get('title', ''),
            identifiers={'nct_id': self.get_source_identifier(raw_data)},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )
    
    def _make_drug_entity(self, raw_data: Dict[str, Any], index: int) -> ExtractedEntity:
        """Helper to create drug entity stub for relationships."""
        interventions = raw_data.get('interventions', [])
        if index < len(interventions):
            drug_name = interventions[index].get('intervention_name', '')
        else:
            drug_name = ''
        
        return ExtractedEntity(
            entity_type=EntityType.DRUG,
            name=drug_name,
            identifiers={},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )
    
    def _make_disease_entity(self, raw_data: Dict[str, Any], index: int) -> ExtractedEntity:
        """Helper to create disease entity stub for relationships."""
        conditions = raw_data.get('conditions', [])
        if isinstance(conditions, str):
            conditions = [conditions]
        
        if index < len(conditions):
            disease_name = conditions[index]
        else:
            disease_name = ''
        
        return ExtractedEntity(
            entity_type=EntityType.DISEASE,
            name=disease_name,
            identifiers={},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )
    
    @staticmethod
    def _parse_phase(phase_str: str) -> int:
        """
        Parse phase string to numeric value.
        
        Args:
            phase_str: Phase string (e.g., "Phase 2", "Phase 1/Phase 2")
            
        Returns:
            Numeric phase (1, 2, 3, 4) or 0 if unparseable
        """
        if not phase_str:
            return 0
        
        phase_str = phase_str.lower()
        
        if 'phase 4' in phase_str or 'phase iv' in phase_str:
            return 4
        elif 'phase 3' in phase_str or 'phase iii' in phase_str:
            return 3
        elif 'phase 2' in phase_str or 'phase ii' in phase_str:
            return 2
        elif 'phase 1' in phase_str or 'phase i' in phase_str:
            return 1
        
        return 0

