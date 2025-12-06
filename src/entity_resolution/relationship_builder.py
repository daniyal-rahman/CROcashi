"""
Relationship builder for creating entity relationships after resolution.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from database.models import (
    CompanyDrug, CompanyOwnershipHistory, DrugIndication, DrugTarget, DrugMechanism,
    TrialSponsor, TrialDrug, TrialDisease, PublicationDrug, PublicationTrial,
    PublicationCompany, RegulatoryDrugEvent, RegulatoryCompanyEvent,
    FilingCompany, FilingDrug, PatentDrug, PatentCompany,
    PresentationDrug, PresentationCompany, PresentationTrial
)
from src.entity_resolution.types import RelationshipExtraction

logger = logging.getLogger(__name__)


class RelationshipBuilder:
    """
    Creates relationships between resolved entities.
    
    Handles:
    - Deduplication (don't create duplicate relationships)
    - Data source tracking (update data_sources JSONB field)
    - Temporal tracking (start_date, end_date)
    """
    
    # Mapping of relationship types to models
    RELATIONSHIP_MODELS = {
        'company_drug': CompanyDrug,
        'company_ownership': CompanyOwnershipHistory,
        'drug_indication': DrugIndication,
        'drug_target': DrugTarget,
        'drug_mechanism': DrugMechanism,
        'trial_sponsor': TrialSponsor,
        'trial_drug': TrialDrug,
        'trial_disease': TrialDisease,
        'publication_drug': PublicationDrug,
        'publication_trial': PublicationTrial,
        'publication_company': PublicationCompany,
        'regulatory_drug_event': RegulatoryDrugEvent,
        'regulatory_company_event': RegulatoryCompanyEvent,
        'filing_company': FilingCompany,
        'filing_drug': FilingDrug,
        'patent_drug': PatentDrug,
        'patent_company': PatentCompany,
        'presentation_drug': PresentationDrug,
        'presentation_company': PresentationCompany,
        'presentation_trial': PresentationTrial,
    }
    
    def __init__(self, session: Session):
        """
        Initialize relationship builder.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.created_count = 0
        self.updated_count = 0
        self.skipped_count = 0
    
    def create_relationship(
        self,
        relationship: RelationshipExtraction,
        source_entity_id: UUID,
        target_entity_id: UUID,
        source_name: str
    ) -> bool:
        """
        Create or update a relationship between entities.
        
        Args:
            relationship: RelationshipExtraction object
            source_entity_id: Resolved source entity UUID
            target_entity_id: Resolved target entity UUID
            source_name: Name of data source
            
        Returns:
            True if relationship created/updated, False otherwise
        """
        model = self.RELATIONSHIP_MODELS.get(relationship.relationship_type)
        if not model:
            logger.warning(f"Unknown relationship type: {relationship.relationship_type}")
            return False
        
        try:
            # Check if relationship already exists in database
            existing = self._find_existing_relationship(
                model,
                source_entity_id,
                target_entity_id,
                relationship.attributes
            )
            
            if existing:
                # Update data_sources
                updated = self._update_data_sources(existing, source_name)
                if updated:
                    self.updated_count += 1
                else:
                    self.skipped_count += 1
                return True
            
            # Check if relationship already exists in current session (not yet committed)
            if self._check_session_for_relationship(model, source_entity_id, target_entity_id):
                self.skipped_count += 1
                logger.debug(f"Skipped duplicate {relationship.relationship_type} in session")
                return True
            
            # Create new relationship
            new_rel = self._create_new_relationship(
                model,
                source_entity_id,
                target_entity_id,
                relationship.attributes,
                relationship.temporal,
                source_name
            )
            
            self.session.add(new_rel)
            self.created_count += 1
            logger.debug(f"Created {relationship.relationship_type} relationship")
            return True
                
        except Exception as e:
            logger.error(f"Error creating relationship: {e}")
            return False
    
    def _find_existing_relationship(
        self,
        model,
        source_id: UUID,
        target_id: UUID,
        attributes: Dict[str, Any]
    ):
        """Find existing relationship in database."""
        # Get ID field names from model
        source_field, target_field = self._get_id_fields(model)
        
        if not source_field or not target_field:
            return None
        
        # Build query
        query = self.session.query(model).filter(
            and_(
                getattr(model, source_field) == source_id,
                getattr(model, target_field) == target_id
            )
        )
        
        # Add temporal filtering if applicable
        if hasattr(model, 'start_date') and 'start_date' in attributes:
            query = query.filter(
                getattr(model, 'start_date') == attributes['start_date']
            )
        
        return query.first()
    
    def _check_session_for_relationship(
        self,
        model,
        source_id: UUID,
        target_id: UUID
    ) -> bool:
        """
        Check if relationship already exists in current session (not yet committed).
        
        This prevents duplicate relationship errors when multiple relationships
        are created in the same transaction.
        """
        source_field, target_field = self._get_id_fields(model)
        
        if not source_field or not target_field:
            return False
        
        # Check new objects in session that haven't been committed yet
        for obj in self.session.new:
            if isinstance(obj, model):
                if (getattr(obj, source_field, None) == source_id and 
                    getattr(obj, target_field, None) == target_id):
                    return True
        
        return False
    
    def _create_new_relationship(
        self,
        model,
        source_id: UUID,
        target_id: UUID,
        attributes: Dict[str, Any],
        temporal: Dict[str, Any],
        source_name: str
    ):
        """Create new relationship instance."""
        # Get ID field names
        source_field, target_field = self._get_id_fields(model)
        
        # Build relationship data
        rel_data = {
            source_field: source_id,
            target_field: target_id,
        }
        
        # Special handling for CompanyDrug: map 'role' to 'relationship_type' or set default
        if model.__name__ == 'CompanyDrug':
            if 'relationship_type' in attributes:
                # Use provided relationship_type
                rel_data['relationship_type'] = attributes['relationship_type']
            elif 'role' in attributes:
                # Map common role values to relationship_type
                role_mapping = {
                    'developer': 'developer',
                    'manufacturer': 'developer',
                    'sponsor': 'developer',
                    'originator': 'originator',
                    'licensee': 'licensee',
                    'acquirer': 'acquirer',
                    'co_developer': 'co_developer'
                }
                role_value = attributes.get('role')
                if role_value in role_mapping:
                    rel_data['relationship_type'] = role_mapping[role_value]
                else:
                    # Default to 'developer' if role not recognized
                    rel_data['relationship_type'] = 'developer'
                    logger.warning(f"Unknown role '{role_value}' for CompanyDrug, defaulting to 'developer'")
            else:
                # No relationship_type or role provided, default to 'developer'
                rel_data['relationship_type'] = 'developer'
                logger.warning("No relationship_type or role provided for CompanyDrug, defaulting to 'developer'")
        
        # Add attributes with constraint validation
        for key, value in attributes.items():
            # Skip 'role' if we already mapped it to 'relationship_type'
            if model.__name__ == 'CompanyDrug' and key == 'role':
                continue
                
            if hasattr(model, key):
                # Validate constraint values before inserting
                if not self._validate_constraint_value(model, key, value):
                    logger.warning(
                        f"Invalid constraint value for {model.__name__}.{key}: {value}. Skipping."
                    )
                    continue
                rel_data[key] = value
        
        # Add temporal data
        for key, value in temporal.items():
            if hasattr(model, key):
                rel_data[key] = value
        
        # Add data_sources tracking
        if hasattr(model, 'data_sources'):
            rel_data['data_sources'] = {
                source_name: {
                    'first_seen': datetime.now().isoformat(),
                    'last_updated': datetime.now().isoformat()
                }
            }
        
        return model(**rel_data)
    
    def _validate_constraint_value(self, model, key: str, value: Any) -> bool:
        """
        Validate that a value meets any database constraints for the field.
        
        Args:
            model: SQLAlchemy model class
            key: Field name
            value: Value to validate
            
        Returns:
            True if value is valid, False otherwise
        """
        # For now, just check basic type constraints
        # More complex constraint validation can be added as needed
        
        # Check if value is None and field is nullable
        if value is None:
            # Check if column is nullable (simplified check)
            # In practice, we'd need to inspect the column
            return True  # Let database handle NULL constraint violations
        
        # Check string length constraints (common constraint)
        if isinstance(value, str):
            # Check for common max length constraints
            max_lengths = {
                'arm_name': 100,  # TrialDrug.arm_name
                'sponsor_role': 50,  # TrialSponsor.sponsor_role
            }
            if key in max_lengths and len(value) > max_lengths[key]:
                logger.warning(f"Value too long for {model.__name__}.{key}: {len(value)} > {max_lengths[key]}")
                return False
        
        # Add more constraint validation as needed
        return True
    
    def _update_data_sources(self, relationship, source_name: str) -> bool:
        """Update data_sources field on existing relationship."""
        if not hasattr(relationship, 'data_sources'):
            return False
        
        data_sources = relationship.data_sources or {}
        
        if source_name in data_sources:
            # Already tracked from this source
            data_sources[source_name]['last_updated'] = datetime.now().isoformat()
            relationship.data_sources = data_sources
            return True
        else:
            # New source for this relationship
            data_sources[source_name] = {
                'first_seen': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat()
            }
            relationship.data_sources = data_sources
            return True
    
    @staticmethod
    def _get_id_fields(model) -> tuple[Optional[str], Optional[str]]:
        """Get the foreign key field names for a relationship model."""
        # Map each model to its ID fields
        id_field_map = {
            'CompanyDrug': ('company_id', 'drug_id'),
            'CompanyOwnershipHistory': ('company_id', 'parent_company_id'),
            'DrugIndication': ('drug_id', 'disease_id'),
            'DrugTarget': ('drug_id', 'target_id'),
            'DrugMechanism': ('drug_id', 'mechanism_id'),
            'TrialSponsor': ('trial_id', 'entity_id'),
            'TrialDrug': ('trial_id', 'drug_id'),
            'TrialDisease': ('trial_id', 'disease_id'),
            'PublicationDrug': ('pub_id', 'drug_id'),
            'PublicationTrial': ('pub_id', 'trial_id'),
            'PublicationCompany': ('pub_id', 'company_id'),
            'RegulatoryDrugEvent': ('event_id', 'drug_id'),
            'RegulatoryCompanyEvent': ('event_id', 'company_id'),
            'FilingCompany': ('filing_id', 'company_id'),
            'FilingDrug': ('filing_id', 'drug_id'),
            'PatentDrug': ('patent_id', 'drug_id'),
            'PatentCompany': ('patent_id', 'company_id'),
            'PresentationDrug': ('presentation_id', 'drug_id'),
            'PresentationCompany': ('presentation_id', 'company_id'),
            'PresentationTrial': ('presentation_id', 'trial_id'),
        }
        
        return id_field_map.get(model.__name__, (None, None))
    
    def get_stats(self) -> Dict[str, int]:
        """Get relationship creation statistics."""
        return {
            'created': self.created_count,
            'updated': self.updated_count,
            'skipped': self.skipped_count,
            'total': self.created_count + self.updated_count + self.skipped_count
        }
    
    def reset_stats(self):
        """Reset statistics."""
        self.created_count = 0
        self.updated_count = 0
        self.skipped_count = 0

