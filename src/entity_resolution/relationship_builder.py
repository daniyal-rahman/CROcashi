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
    FilingCompany, FilingDrug, PatentDrug, PatentCompany
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
            # Check if relationship already exists
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
            else:
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
        
        # Add attributes
        for key, value in attributes.items():
            if hasattr(model, key):
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

