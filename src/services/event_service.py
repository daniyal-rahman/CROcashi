"""
Event service for creating and managing events in the unified event stream.
"""
import logging
from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from database.models.events import Event
from database.models.sources import Source

logger = logging.getLogger(__name__)


class EventService:
    """Service for creating and managing events in the unified event stream."""
    
    # Event type mappings for hierarchical naming
    EVENT_TYPE_MAPPINGS = {
        # Trial events
        'trial_initiated': 'trial.status.initiated',
        'trial_recruiting': 'trial.status.recruiting',
        'trial_active': 'trial.status.active',
        'trial_completed': 'trial.status.completed',
        'trial_terminated': 'trial.status.terminated',
        'trial_withdrawn': 'trial.status.withdrawn',
        'trial_suspended': 'trial.status.suspended',
        
        # Program milestones
        'program_preclinical': 'program.milestone.preclinical',
        'program_phase_1': 'program.milestone.phase_1',
        'program_phase_2': 'program.milestone.phase_2',
        'program_phase_3': 'program.milestone.phase_3',
        'program_nda_filed': 'program.milestone.nda_filed',
        'program_approved': 'program.milestone.approved',
        'program_rejected': 'program.milestone.rejected',
        
        # Corporate events
        'corporate_founded': 'corporate.founded',
        'corporate_funded': 'corporate.funded',
        'corporate_acquired': 'corporate.acquired',
        'corporate_dissolved': 'corporate.dissolved',
        'corporate_layoff': 'corporate.layoff',
        
        # Regulatory events
        'regulatory_ind_filed': 'regulatory.ind_filed',
        'regulatory_clinical_hold': 'regulatory.clinical_hold',
        'regulatory_breakthrough': 'regulatory.breakthrough',
        'regulatory_approval': 'regulatory.approval',
        'regulatory_rejection': 'regulatory.rejection',
        
        # Publication events
        'publication_abstract': 'publication.abstract',
        'publication_published': 'publication.published',
        'publication_retracted': 'publication.retracted',
        
        # Personnel events
        'personnel_key_hire': 'personnel.key_hire',
        'personnel_key_departure': 'personnel.key_departure',
    }
    
    # Significance levels for different event types
    SIGNIFICANCE_MAPPINGS = {
        'critical': [
            'trial.status.terminated',
            'trial.status.withdrawn',
            'program.milestone.approved',
            'program.milestone.rejected',
            'corporate.acquired',
            'corporate.dissolved',
            'regulatory.approval',
            'regulatory.rejection',
        ],
        'major': [
            'trial.status.initiated',
            'trial.status.completed',
            'program.milestone.phase_1',
            'program.milestone.phase_2',
            'program.milestone.phase_3',
            'program.milestone.nda_filed',
            'corporate.founded',
            'corporate.funded',
            'corporate.layoff',  # Layoffs are major financial distress signals
            'regulatory.ind_filed',
            'regulatory.clinical_hold',
            'regulatory.breakthrough',
            'personnel.key_hire',
            'personnel.key_departure',
        ],
        'minor': [
            'trial.status.recruiting',
            'trial.status.active',
            'trial.status.suspended',
            'publication.published',
        ],
    }
    
    def __init__(self, session: Session):
        """Initialize event service."""
        self.session = session
    
    def _get_significance(self, event_type: str) -> str:
        """Determine event significance level."""
        for significance, event_types in self.SIGNIFICANCE_MAPPINGS.items():
            if event_type in event_types:
                return significance
        return 'minor'  # Default to minor if not specified
    
    def create_event(
        self,
        event_type: str,
        event_date: date,
        entities_involved: List[UUID],
        event_data: Optional[Dict] = None,
        source_id: Optional[UUID] = None,
        confidence_score: Optional[float] = None,
        discovered_at: Optional[datetime] = None,
        related_event_ids: Optional[List[UUID]] = None
    ) -> Event:
        """
        Create a new event in the unified event stream.
        
        Args:
            event_type: Hierarchical event type (e.g., 'trial.status.terminated')
            event_date: When the event occurred
            entities_involved: List of entity IDs involved
            event_data: Optional flexible JSONB data
            source_id: Optional source ID
            confidence_score: Optional confidence score (0-1)
            discovered_at: When we discovered this event (defaults to now)
            related_event_ids: Optional list of related event IDs
            
        Returns:
            Created Event object
        """
        # Validate inputs
        if not entities_involved:
            raise ValueError("entities_involved cannot be empty - events must involve at least one entity")
        
        if confidence_score is not None and (confidence_score < 0 or confidence_score > 1):
            raise ValueError(f"confidence_score must be between 0 and 1, got {confidence_score}")
        
        # Validate source_id exists if provided
        if source_id:
            source = self.session.query(Source).filter(
                Source.source_id == source_id,
                Source.deleted_at.is_(None)
            ).first()
            if not source:
                raise ValueError(f"Source {source_id} not found")
        
        # Determine significance
        event_significance = self._get_significance(event_type)
        
        # Default discovered_at to now
        if discovered_at is None:
            discovered_at = datetime.now()
        
        event = Event(
            event_type=event_type,
            event_significance=event_significance,
            event_date=event_date,
            entities_involved=entities_involved,
            event_data=event_data or {},
            source_id=source_id,
            confidence_score=confidence_score,
            discovered_at=discovered_at,
            related_event_ids=related_event_ids or []
        )
        
        self.session.add(event)
        return event
    
    def convert_regulatory_event_to_event(
        self,
        regulatory_event_id: UUID,
        entities_involved: List[UUID],
        source_id: Optional[UUID] = None
    ) -> Event:
        """
        Convert an existing RegulatoryEvent to the unified Event format.
        
        This is used for backfilling events from existing regulatory_events table.
        """
        from database.models.clinical import RegulatoryEvent
        
        reg_event = self.session.query(RegulatoryEvent).filter(
            RegulatoryEvent.event_id == regulatory_event_id
        ).first()
        
        if not reg_event:
            raise ValueError(f"RegulatoryEvent {regulatory_event_id} not found")
        
        # Map regulatory event type to event type
        event_type_map = {
            'approval': 'regulatory.approval',
            'rejection': 'regulatory.rejection',
            'breakthrough': 'regulatory.breakthrough',
            'orphan': 'regulatory.orphan',
            'fast_track': 'regulatory.fast_track',
            'clinical_hold': 'regulatory.clinical_hold',
            'withdrawal': 'regulatory.withdrawal',
        }
        
        # Add missing mappings
        if reg_event.event_type not in event_type_map:
            # Default mapping for unknown types
            event_type_map[reg_event.event_type] = f'regulatory.{reg_event.event_type}'
        
        event_type = event_type_map.get(reg_event.event_type, f'regulatory.{reg_event.event_type}')
        
        # Build event data
        event_data = {
            'regulatory_body': reg_event.regulatory_body,
            'country': reg_event.country,
            'application_number': reg_event.application_number,
            'approval_type': reg_event.approval_type,
            'description': reg_event.description,
            'document_url': reg_event.document_url,
        }
        
        return self.create_event(
            event_type=event_type,
            event_date=reg_event.event_date,
            entities_involved=entities_involved,
            event_data=event_data,
            source_id=source_id,
            discovered_at=reg_event.created_at
        )
    
    def convert_trial_status_to_event(
        self,
        trial_id: UUID,
        status: str,
        status_date: date,
        entities_involved: List[UUID],
        source_id: Optional[UUID] = None
    ) -> Event:
        """
        Convert a trial status change to an event.
        
        This is used for backfilling events from TrialStatusHistory.
        """
        # Map status to event type
        status_map = {
            'recruiting': 'trial.status.recruiting',
            'active': 'trial.status.active',
            'active_not_recruiting': 'trial.status.active',
            'completed': 'trial.status.completed',
            'terminated': 'trial.status.terminated',
            'withdrawn': 'trial.status.withdrawn',
            'suspended': 'trial.status.suspended',
            'not_yet_recruiting': 'trial.status.initiated',
            'enrolling_by_invitation': 'trial.status.recruiting',
        }
        
        event_type = status_map.get(status.lower(), f'trial.status.{status.lower()}')
        
        event_data = {
            'trial_id': str(trial_id),
            'status': status,
        }
        
        return self.create_event(
            event_type=event_type,
            event_date=status_date,
            entities_involved=entities_involved,
            event_data=event_data,
            source_id=source_id
        )

