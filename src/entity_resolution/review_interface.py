"""
Review interface for manual resolution of ambiguous matches.

Provides tools for reviewing entity match candidates and making decisions.
"""
import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_
from sqlalchemy.orm import Session

from database.models import (
    EntityMatchCandidate, EntityAlias, Company, Drug, Disease,
    Target, ClinicalTrial, Publication, Institution
)
from src.entity_resolution.types import EntityType

logger = logging.getLogger(__name__)


class ReviewInterface:
    """
    Interface for reviewing and resolving ambiguous entity matches.
    
    Supports:
    - Viewing pending matches
    - Confirming matches
    - Rejecting matches (create new entity)
    - Creating negative match rules
    """
    
    # Entity models for lookups
    ENTITY_MODELS = {
        EntityType.COMPANY: Company,
        EntityType.INSTITUTION: Institution,
        EntityType.DRUG: Drug,
        EntityType.DISEASE: Disease,
        EntityType.TARGET: Target,
        EntityType.TRIAL: ClinicalTrial,
        EntityType.PUBLICATION: Publication,
    }
    
    def __init__(self, session: Session):
        """
        Initialize review interface.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    def get_pending_reviews(
        self,
        entity_type: Optional[EntityType] = None,
        limit: int = 50
    ) -> List[EntityMatchCandidate]:
        """
        Get list of entity matches needing review.
        
        Args:
            entity_type: Filter by entity type (optional)
            limit: Maximum number of results
            
        Returns:
            List of EntityMatchCandidate objects
        """
        query = self.session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.status == 'needs_review'
        )
        
        if entity_type:
            query = query.filter(
                EntityMatchCandidate.entity_type == entity_type.value
            )
        
        query = query.order_by(EntityMatchCandidate.created_at.desc()).limit(limit)
        
        return query.all()
    
    def get_candidate_details(self, candidate_id: UUID) -> dict:
        """
        Get detailed information about a match candidate.
        
        Args:
            candidate_id: UUID of the candidate
            
        Returns:
            Dict with candidate details and potential matches
        """
        candidate = self.session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.candidate_id == candidate_id
        ).first()
        
        if not candidate:
            return {'error': 'Candidate not found'}
        
        # Get details about potential matches
        potential_matches = []
        if candidate.potential_matches:
            for match in candidate.potential_matches:
                entity_id = UUID(match['entity_id'])
                entity_details = self._get_entity_details(
                    candidate.entity_type,
                    entity_id
                )
                potential_matches.append({
                    **match,
                    'entity_details': entity_details
                })
        
        return {
            'candidate_id': str(candidate.candidate_id),
            'entity_type': candidate.entity_type,
            'source_name': candidate.source_name,
            'source_identifier': candidate.source_identifier,
            'extracted_text': candidate.extracted_text,
            'extracted_context': candidate.extracted_context,
            'potential_matches': potential_matches,
            'match_confidence': float(candidate.match_confidence) if candidate.match_confidence else None,
            'match_reasoning': candidate.match_reasoning,
            'created_at': candidate.created_at.isoformat() if candidate.created_at else None
        }
    
    def confirm_match(
        self,
        candidate_id: UUID,
        entity_id: UUID,
        reviewer_name: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Confirm a match and update the candidate.
        
        Args:
            candidate_id: UUID of the candidate
            entity_id: UUID of the matched entity
            reviewer_name: Name/ID of reviewer
            notes: Optional review notes
            
        Returns:
            True if successful
        """
        candidate = self.session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.candidate_id == candidate_id
        ).first()
        
        if not candidate:
            logger.error(f"Candidate {candidate_id} not found")
            return False
        
        try:
            # Update candidate
            candidate.matched_to = entity_id
            candidate.status = 'reviewed'
            candidate.reviewed_by = reviewer_name
            candidate.reviewed_at = datetime.now().date()
            candidate.review_notes = notes
            candidate.match_method = 'manual'
            candidate.match_confidence = 1.0  # Manual review is highest confidence
            
            # Create alias for future matching
            self._create_alias(
                candidate.entity_type,
                entity_id,
                candidate.extracted_text,
                'manual_review',
                candidate.source_name
            )
            
            self.session.commit()
            logger.info(f"Confirmed match for candidate {candidate_id}")
            return True
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error confirming match: {e}")
            return False
    
    def reject_match(
        self,
        candidate_id: UUID,
        reviewer_name: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Reject all matches and mark for new entity creation.
        
        Args:
            candidate_id: UUID of the candidate
            reviewer_name: Name/ID of reviewer
            notes: Optional review notes
            
        Returns:
            True if successful
        """
        candidate = self.session.query(EntityMatchCandidate).filter(
            EntityMatchCandidate.candidate_id == candidate_id
        ).first()
        
        if not candidate:
            logger.error(f"Candidate {candidate_id} not found")
            return False
        
        try:
            candidate.matched_to = None
            candidate.status = 'new_entity'
            candidate.reviewed_by = reviewer_name
            candidate.reviewed_at = datetime.now().date()
            candidate.review_notes = notes
            
            self.session.commit()
            logger.info(f"Rejected all matches for candidate {candidate_id}")
            return True
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Error rejecting match: {e}")
            return False
    
    def get_review_stats(self) -> dict:
        """
        Get statistics about the review queue.
        
        Returns:
            Dict with review statistics
        """
        from sqlalchemy import func
        
        # Count by status
        status_counts = self.session.query(
            EntityMatchCandidate.status,
            func.count(EntityMatchCandidate.candidate_id)
        ).group_by(EntityMatchCandidate.status).all()
        
        # Count by entity type
        type_counts = self.session.query(
            EntityMatchCandidate.entity_type,
            func.count(EntityMatchCandidate.candidate_id)
        ).filter(
            EntityMatchCandidate.status == 'needs_review'
        ).group_by(EntityMatchCandidate.entity_type).all()
        
        return {
            'status_counts': {status: count for status, count in status_counts},
            'needs_review_by_type': {etype: count for etype, count in type_counts},
            'total_pending': sum(count for status, count in status_counts if status == 'needs_review')
        }
    
    def _get_entity_details(self, entity_type: str, entity_id: UUID) -> dict:
        """Get details about an entity from the database."""
        try:
            entity_type_enum = EntityType(entity_type)
            model = self.ENTITY_MODELS.get(entity_type_enum)
            
            if not model:
                return {'error': 'Unknown entity type'}
            
            # Query the entity
            id_field = self._get_id_field(model)
            entity = self.session.query(model).filter(
                getattr(model, id_field) == entity_id
            ).first()
            
            if not entity:
                return {'error': 'Entity not found'}
            
            # Get name field
            name_field = self._get_name_field(model)
            name = getattr(entity, name_field, 'Unknown')
            
            # Get additional relevant fields
            details = {'name': name}
            
            # Add type-specific fields
            if entity_type_enum == EntityType.COMPANY:
                details['ticker'] = entity.ticker
                details['status'] = entity.status
            elif entity_type_enum == EntityType.DRUG:
                details['generic_name'] = entity.generic_name
                details['drug_type'] = entity.drug_type
            elif entity_type_enum == EntityType.TRIAL:
                details['nct_id'] = entity.nct_id
                details['phase'] = entity.phase
                details['status'] = entity.status
            
            return details
            
        except Exception as e:
            logger.error(f"Error getting entity details: {e}")
            return {'error': str(e)}
    
    def _create_alias(
        self,
        entity_type: str,
        entity_id: UUID,
        alias_text: str,
        alias_type: str,
        source: str
    ):
        """Create an alias entry for future matching."""
        # Check if alias already exists
        existing = self.session.query(EntityAlias).filter(
            and_(
                EntityAlias.entity_type == entity_type,
                EntityAlias.entity_id == entity_id,
                EntityAlias.alias_text == alias_text
            )
        ).first()
        
        if existing:
            return  # Alias already exists
        
        # Create new alias
        alias = EntityAlias(
            entity_type=entity_type,
            entity_id=entity_id,
            alias_text=alias_text,
            alias_type=alias_type,
            source=source,
            confidence_score=1.0  # Manual confirmation = high confidence
        )
        
        self.session.add(alias)
    
    @staticmethod
    def _get_id_field(model) -> str:
        """Get the ID field name for a model."""
        id_fields = {
            'Company': 'company_id',
            'Institution': 'institution_id',
            'Drug': 'drug_id',
            'Disease': 'disease_id',
            'Target': 'target_id',
            'ClinicalTrial': 'trial_id',
            'Publication': 'pub_id',
        }
        return id_fields.get(model.__name__, 'id')
    
    @staticmethod
    def _get_name_field(model) -> str:
        """Get the name field for a model."""
        name_fields = {
            'Company': 'name',
            'Institution': 'name',
            'Drug': 'primary_name',
            'Disease': 'disease_name',
            'Target': 'target_name',
            'ClinicalTrial': 'trial_title',
            'Publication': 'title',
        }
        return name_fields.get(model.__name__, 'name')

