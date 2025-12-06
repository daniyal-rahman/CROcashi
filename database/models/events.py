"""
Unified event stream models for event-driven architecture.
"""
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import ARRAY, CheckConstraint, Column, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database.models.base import BaseModel


class Event(BaseModel):
    """
    Unified event stream for all significant events in the biotech ecosystem.
    
    Uses hierarchical event naming (e.g., 'trial.status.terminated') and
    significance levels (critical, major, minor, trace) to support flexible
    querying and filtering.
    
    Initial focus: Capture significant events only (critical and major).
    Design supports fine-grained events later if needed.
    """
    
    __tablename__ = 'events'
    
    event_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    event_type = Column(
        String(200),
        nullable=False,
        index=True,
        comment='Hierarchical naming: trial.status.terminated, program.milestone.phase_2_complete, corporate.acquired'
    )
    event_significance = Column(
        String(20),
        nullable=False,
        index=True,
        comment='critical, major, minor, trace'
    )
    event_date = Column(
        Date,
        nullable=False,
        index=True,
        comment='When the event occurred'
    )
    entities_involved = Column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        comment='Array of entity_ids involved in this event'
    )
    event_data = Column(
        JSONB,
        nullable=True,
        comment='Flexible schema per event type - stores event-specific details'
    )
    source_id = Column(
        UUID(as_uuid=True),
        ForeignKey('sources.source_id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    confidence_score = Column(
        Numeric(3, 2),
        nullable=True,
        comment='0-1 confidence score for this event'
    )
    discovered_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment='When we first detected/learned about this event'
    )
    related_event_ids = Column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment='Array of related event_ids (e.g., trial termination related to enrollment issues)'
    )
    
    source = relationship('Source', backref='events')
    
    __table_args__ = (
        CheckConstraint(
            "event_significance IN ('critical', 'major', 'minor', 'trace')",
            name='check_event_significance'
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name='check_event_confidence_score'
        ),
        {'comment': 'Unified event stream for event-driven architecture'}
    )

