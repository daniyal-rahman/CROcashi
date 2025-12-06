"""
Clinical trial and regulatory event models.
"""
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, Column, Date, ForeignKey,
    Integer, String, Text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database.models.base import BaseModel


class ClinicalTrial(BaseModel):
    """Clinical trial entity."""
    
    __tablename__ = 'clinical_trials'
    
    trial_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    nct_id = Column(
        String(50),
        unique=True,
        nullable=True,
        index=True,
        comment='ClinicalTrials.gov identifier'
    )
    eudract_number = Column(String(50), nullable=True, index=True)
    trial_title = Column(Text, nullable=True)
    
    phase = Column(
        String(50),
        nullable=True,
        index=True,
        comment='Phase 1, Phase 2, etc.'
    )
    phase_numeric = Column(
        Integer,
        nullable=True,
        index=True,
        comment='1, 2, 3 for filtering'
    )
    study_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='interventional, observational'
    )
    
    enrollment_target = Column(Integer, nullable=True)
    enrollment_actual = Column(Integer, nullable=True)
    
    registration_date = Column(Date, nullable=True, index=True)
    start_date = Column(Date, nullable=True, index=True)
    primary_completion_date = Column(Date, nullable=True, index=True)
    completion_date = Column(Date, nullable=True, index=True)
    
    status = Column(
        String(50),
        nullable=True,
        index=True,
        comment='recruiting, active, completed, terminated, suspended, withdrawn'
    )
    status_verified_date = Column(Date, nullable=True)
    why_stopped = Column(Text, nullable=True, comment='Termination reason')
    
    allocation = Column(String(50), nullable=True)
    intervention_model = Column(String(50), nullable=True)
    masking = Column(String(50), nullable=True)
    primary_purpose = Column(String(50), nullable=True)
    
    primary_endpoints = Column(ARRAY(Text), nullable=True)
    secondary_endpoints = Column(ARRAY(Text), nullable=True)
    study_locations = Column(ARRAY(Text), nullable=True)
    
    results_posted = Column(Boolean, default=False, index=True)
    results_summary = Column(Text, nullable=True)
    results_url = Column(String(1000), nullable=True)
    
    sponsor_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='industry, academic, government, mixed'
    )
    
    data_sources = Column(JSONB, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "study_type IN ('interventional', 'observational') OR study_type IS NULL",
            name='check_study_type'
        ),
        CheckConstraint(
            "status IN ('recruiting', 'active', 'completed', 'terminated', 'suspended', 'withdrawn', 'unknown', 'enrolling_by_invitation', 'active_not_recruiting', 'not_yet_recruiting') OR status IS NULL",
            name='check_trial_status'
        ),
        CheckConstraint(
            "sponsor_type IN ('industry', 'academic', 'government', 'mixed') OR sponsor_type IS NULL",
            name='check_sponsor_type'
        ),
    )


class TrialStatusHistory(BaseModel):
    """Temporal tracking of clinical trial status changes."""
    
    __tablename__ = 'trial_status_history'
    
    history_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    trial_id = Column(
        UUID(as_uuid=True),
        ForeignKey('clinical_trials.trial_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    status = Column(
        String(50),
        nullable=False,
        index=True,
        comment='recruiting, active, completed, terminated, suspended, withdrawn, etc.'
    )
    status_date = Column(
        Date,
        nullable=False,
        index=True,
        comment='Date when this status was recorded'
    )
    source = Column(
        String(200),
        nullable=True,
        comment='Source of the status change (e.g., clinicaltrials_gov)'
    )
    notes = Column(Text, nullable=True, comment='Additional notes about the status change')
    
    trial = relationship('ClinicalTrial', backref='status_history')
    
    __table_args__ = (
        CheckConstraint(
            "status IN ('recruiting', 'active', 'completed', 'terminated', 'suspended', 'withdrawn', 'unknown', 'enrolling_by_invitation', 'active_not_recruiting', 'not_yet_recruiting') OR status IS NOT NULL",
            name='check_status_history_status'
        ),
    )


class RegulatoryEvent(BaseModel):
    """Regulatory events (approvals, designations, etc.)."""
    
    __tablename__ = 'regulatory_events'
    
    event_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    event_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='approval, rejection, breakthrough, orphan, fast_track, clinical_hold, withdrawal'
    )
    event_date = Column(
        Date,
        nullable=False,
        index=True
    )
    regulatory_body = Column(
        String(50),
        nullable=False,
        index=True,
        comment='FDA, EMA, PMDA, Health_Canada'
    )
    country = Column(String(100), nullable=True, index=True)
    
    application_number = Column(
        String(200),
        nullable=True,
        comment='NDA/BLA number'
    )
    approval_type = Column(
        String(50),
        nullable=True,
        comment='full, accelerated, priority_review'
    )
    
    description = Column(Text, nullable=True)
    document_url = Column(String(1000), nullable=True)
    
    data_sources = Column(JSONB, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('approval', 'rejection', 'breakthrough', 'orphan', 'fast_track', 'clinical_hold', 'withdrawal')",
            name='check_event_type'
        ),
        CheckConstraint(
            "regulatory_body IN ('FDA', 'EMA', 'PMDA', 'Health_Canada') OR regulatory_body IS NOT NULL",
            name='check_regulatory_body'
        ),
        CheckConstraint(
            "approval_type IN ('full', 'accelerated', 'priority_review') OR approval_type IS NULL",
            name='check_approval_type'
        ),
    )

