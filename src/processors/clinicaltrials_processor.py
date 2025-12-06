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
    
    def _normalize_api_response(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize ClinicalTrials.gov API response to flat structure.
        
        Handles both:
        - Legacy flat format (test data, backwards compatibility)
        - Current nested protocolSection format (real API)
        
        Args:
            raw_data: Raw API response
            
        Returns:
            Normalized flat structure
        """
        # If already flat (test data), return as-is
        if 'nct_id' in raw_data or 'NCTId' in raw_data:
            return raw_data
        
        # Check if this is nested protocolSection format
        if 'protocolSection' not in raw_data:
            logger.warning("Unexpected data format - no 'nct_id' or 'protocolSection'")
            return raw_data
        
        # Extract from nested protocolSection structure
        protocol = raw_data.get('protocolSection', {})
        id_module = protocol.get('identificationModule', {})
        status_module = protocol.get('statusModule', {})
        sponsor_module = protocol.get('sponsorCollaboratorsModule', {})
        design_module = protocol.get('designModule', {})
        arms_module = protocol.get('armsInterventionsModule', {})
        conditions_module = protocol.get('conditionsModule', {})
        
        # Map to flat structure expected by extraction methods
        normalized = {
            'nct_id': id_module.get('nctId', ''),
            'brief_title': id_module.get('briefTitle', ''),
            'title': id_module.get('briefTitle', ''),  # Alias
            'official_title': id_module.get('officialTitle', ''),
            'overall_status': status_module.get('overallStatus', ''),
            'start_date': status_module.get('startDateStruct', {}).get('date'),
            'completion_date': status_module.get('completionDateStruct', {}).get('date'),
            'primary_completion_date': status_module.get('primaryCompletionDateStruct', {}).get('date'),
            'phase': design_module.get('phases', [''])[0] if design_module.get('phases') else '',
            'study_type': design_module.get('studyType', ''),
            'enrollment': {
                'value': status_module.get('enrollmentInfo', {}).get('count')
            },
            'why_stopped': status_module.get('whyStopped', ''),
            'sponsor': {
                'lead_sponsor': {
                    'agency': sponsor_module.get('leadSponsor', {}).get('name', ''),
                    'agency_class': sponsor_module.get('leadSponsor', {}).get('class', '')
                },
                'collaborators': [
                    {
                        'agency': c.get('name', ''),
                        'agency_class': c.get('class', '')
                    }
                    for c in sponsor_module.get('collaborators', [])
                ]
            },
            'interventions': [
                {
                    'intervention_type': interv.get('type', '').lower(),
                    'intervention_name': interv.get('name', ''),
                    'other_names': interv.get('otherNames', []),
                    'description': interv.get('description', '')
                }
                for interv in arms_module.get('interventions', [])
            ],
            'conditions': conditions_module.get('conditions', [])
        }
        
        return normalized
    
    def get_source_identifier(self, raw_data: Dict[str, Any]) -> str:
        """
        Get NCT ID from trial data.
        
        Args:
            raw_data: Raw trial data
            
        Returns:
            NCT ID (e.g., "NCT12345678")
        """
        # Handle nested protocolSection format
        if 'protocolSection' in raw_data:
            protocol = raw_data.get('protocolSection', {})
            id_module = protocol.get('identificationModule', {})
            return id_module.get('nctId', '')
        
        # Handle flat format (backwards compatibility)
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
        
        # Normalize API response format
        data = self._normalize_api_response(raw_data)
        
        entities = {
            'trials': [],
            'companies': [],
            'institutions': [],
            'drugs': [],
            'diseases': []
        }
        
        nct_id = self.get_source_identifier(raw_data)
        
        try:
            # Extract trial entity (use normalized data)
            trial = self._extract_trial(data)
            if trial:
                entities['trials'].append(trial)
                self.metrics.entities_extracted += 1
            
            # Extract sponsor (lead sponsor) (use normalized data)
            sponsor = self._extract_sponsor(data)
            if sponsor:
                if sponsor.entity_type == EntityType.COMPANY:
                    entities['companies'].append(sponsor)
                else:
                    entities['institutions'].append(sponsor)
                self.metrics.entities_extracted += 1
            
            # Extract collaborators (use normalized data)
            collaborators = self._extract_collaborators(data)
            for collab in collaborators:
                if collab.entity_type == EntityType.COMPANY:
                    entities['companies'].append(collab)
                else:
                    entities['institutions'].append(collab)
                self.metrics.entities_extracted += 1
            
            # Extract interventions (drugs) (use normalized data)
            drugs = self._extract_interventions(data)
            entities['drugs'].extend(drugs)
            self.metrics.entities_extracted += len(drugs)
            
            # Extract conditions (diseases) (use normalized data)
            diseases = self._extract_conditions(data)
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
        resolved_entities: Dict[str, UUID],
        id_to_entity: Dict[UUID, ExtractedEntity]
    ) -> List[RelationshipExtraction]:
        """
        Extract relationships after entities are resolved.
        
        Args:
            raw_data: Raw trial data
            resolved_entities: Map of entity keys to resolved UUIDs
            id_to_entity: Map of resolved UUIDs to their extracted entities
            
        Returns:
            List of relationships to create
        """
        relationships = []
        
        trial_id = resolved_entities.get('trial')
        if not trial_id:
            logger.warning("No trial ID found in resolved entities")
            return relationships
        
        # Get trial entity for relationship stubs
        trial_entity = id_to_entity.get(trial_id)
        if not trial_entity:
            # Fallback: create from raw data
            trial_entity = self._make_trial_entity(raw_data)
        
        # Create trial sponsor relationships
        if 'sponsor' in resolved_entities:
            sponsor_id = resolved_entities['sponsor']
            sponsor_entity = id_to_entity.get(sponsor_id)
            if sponsor_entity:
                relationships.append(self._create_sponsor_relationship_from_entity(
                    trial_entity,
                    sponsor_entity,
                    'lead_sponsor'
                ))
        
        # Create collaborator relationships
        for collab_id in resolved_entities.get('collaborators', []):
            collab_entity = id_to_entity.get(collab_id)
            if collab_entity:
                relationships.append(self._create_sponsor_relationship_from_entity(
                    trial_entity,
                    collab_entity,
                    'collaborator'
                ))
        
        # Create trial-drug relationships using actual extracted entities
        for drug_id in resolved_entities.get('drugs', []):
            drug_entity = id_to_entity.get(drug_id)
            if drug_entity:
                # Get arm_name from drug entity's context if available
                arm_groups = drug_entity.context.get('arm_groups', [])
                arm_name = arm_groups[0] if arm_groups else 'experimental'
                
                relationships.append(RelationshipExtraction(
                    relationship_type='trial_drug',
                    source_entity=trial_entity,
                    target_entity=drug_entity,
                    attributes={
                        'arm_name': arm_name
                    }
                ))
        
        # Create trial-disease relationships using actual extracted entities
        for disease_id in resolved_entities.get('diseases', []):
            disease_entity = id_to_entity.get(disease_id)
            if disease_entity:
                relationships.append(RelationshipExtraction(
                    relationship_type='trial_disease',
                    source_entity=trial_entity,
                    target_entity=disease_entity,
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
    
    def _create_sponsor_relationship_from_entity(
        self,
        trial_entity: ExtractedEntity,
        sponsor_entity: ExtractedEntity,
        role: str
    ) -> RelationshipExtraction:
        """Create a trial sponsor relationship from extracted entities."""
        # Determine entity type from the sponsor entity
        is_company = sponsor_entity.entity_type == EntityType.COMPANY
        
        return RelationshipExtraction(
            relationship_type='trial_sponsor',
            source_entity=trial_entity,
            target_entity=sponsor_entity,
            attributes={
                'entity_type': 'company' if is_company else 'institution',
                'sponsor_role': role,
                'is_regulatory_sponsor': True,
                'is_financial_sponsor': True
            },
            temporal={}
        )
    
    def _make_trial_entity(self, raw_data: Dict[str, Any]) -> ExtractedEntity:
        """Helper to create trial entity stub for relationships."""
        # Use normalized data format (same as extraction)
        data = self._normalize_api_response(raw_data)
        return ExtractedEntity(
            entity_type=EntityType.TRIAL,
            name=data.get('title', data.get('brief_title', '')),
            identifiers={'nct_id': self.get_source_identifier(raw_data)},
            context={},
            source_name=self.SOURCE_NAME,
            source_identifier=self.get_source_identifier(raw_data)
        )
    
    def _make_drug_entity(self, raw_data: Dict[str, Any], index: int) -> ExtractedEntity:
        """Helper to create drug entity stub for relationships."""
        # Use normalized data format (same as extraction)
        data = self._normalize_api_response(raw_data)
        interventions = data.get('interventions', [])
        
        if index < len(interventions):
            drug_name = interventions[index].get('intervention_name', interventions[index].get('name', ''))
            # Normalize drug name (same as in _extract_interventions)
            drug_name = self.normalize_drug_name(drug_name)
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
        # Use normalized data format (same as extraction)
        data = self._normalize_api_response(raw_data)
        conditions = data.get('conditions', [])
        if isinstance(conditions, str):
            conditions = [conditions]
        
        if index < len(conditions):
            disease_name = conditions[index]
            # Clean up condition name (same as in _extract_conditions)
            disease_name = disease_name.strip()
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
            phase_str: Phase string (e.g., "Phase 2", "PHASE2", "Phase 1/Phase 2")

        Returns:
            Numeric phase (1, 2, 3, 4) or 0 if unparseable
        """
        if not phase_str:
            return 0

        phase_str = phase_str.lower()

        # Handle both "phase 4" and "phase4" formats
        if 'phase 4' in phase_str or 'phase4' in phase_str or 'phase iv' in phase_str:
            return 4
        elif 'phase 3' in phase_str or 'phase3' in phase_str or 'phase iii' in phase_str:
            return 3
        elif 'phase 2' in phase_str or 'phase2' in phase_str or 'phase ii' in phase_str:
            return 2
        elif 'phase 1' in phase_str or 'phase1' in phase_str or 'phase i' in phase_str:
            return 1

        return 0

