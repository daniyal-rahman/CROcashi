"""
Publication, patent, conference, and SEC filing models.
"""
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import (
    ARRAY, Boolean, CheckConstraint, Column, Date, Numeric,
    ForeignKey, Integer, String, Text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database.models.base import BaseModel


class Publication(BaseModel):
    """Scientific publications."""
    
    __tablename__ = 'publications'
    
    pub_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    pmid = Column(
        String(50),
        unique=True,
        nullable=True,
        index=True,
        comment='PubMed ID'
    )
    pmcid = Column(String(50), nullable=True, index=True)
    doi = Column(String(200), nullable=True, index=True)
    
    title = Column(Text, nullable=False, index=True)
    abstract = Column(Text, nullable=True)
    journal = Column(String(500), nullable=True, index=True)
    publication_date = Column(Date, nullable=True, index=True)
    
    publication_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='clinical_trial, review, meta_analysis, case_report'
    )
    
    is_clinical_trial_result = Column(Boolean, default=False, index=True)
    mentions_safety_issues = Column(Boolean, default=False, index=True)
    mentions_efficacy_failure = Column(Boolean, default=False, index=True)
    
    full_text_url = Column(String(1000), nullable=True)
    pdf_url = Column(String(1000), nullable=True)
    
    data_sources = Column(JSONB, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "publication_type IN ('clinical_trial', 'review', 'meta_analysis', 'case_report') OR publication_type IS NULL",
            name='check_publication_type'
        ),
    )


class Patent(BaseModel):
    """Patent entities."""
    
    __tablename__ = 'patents'
    
    patent_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    patent_number = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )
    patent_office = Column(
        String(50),
        nullable=False,
        index=True,
        comment='USPTO, EPO, etc.'
    )
    
    filing_date = Column(Date, nullable=True, index=True)
    publication_date = Column(Date, nullable=True, index=True)
    grant_date = Column(Date, nullable=True, index=True)
    expiration_date = Column(Date, nullable=True, index=True)
    abandonment_date = Column(Date, nullable=True)
    
    status = Column(
        String(50),
        nullable=True,
        index=True,
        comment='pending, granted, expired, abandoned'
    )
    
    title = Column(Text, nullable=True)
    abstract = Column(Text, nullable=True)
    inventors = Column(ARRAY(Text), nullable=True)
    assignees = Column(ARRAY(Text), nullable=True)
    
    data_sources = Column(JSONB, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'granted', 'expired', 'abandoned') OR status IS NULL",
            name='check_patent_status'
        ),
    )


class Conference(BaseModel):
    """Conference entities."""
    
    __tablename__ = 'conferences'
    
    conference_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    conference_name = Column(
        String(500),
        nullable=False,
        index=True
    )
    conference_date = Column(Date, nullable=True, index=True)
    location = Column(String(500), nullable=True)


class ConferencePresentation(BaseModel):
    """Conference presentations."""
    
    __tablename__ = 'conference_presentations'
    
    presentation_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    conference_id = Column(
        UUID(as_uuid=True),
        ForeignKey('conferences.conference_id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    abstract_number = Column(String(100), nullable=True, index=True)
    presentation_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='oral, poster, late_breaking'
    )
    
    title = Column(Text, nullable=True)
    abstract = Column(Text, nullable=True)
    authors = Column(ARRAY(Text), nullable=True)
    presentation_date = Column(Date, nullable=True, index=True)
    
    status = Column(
        String(50),
        nullable=True,
        index=True,
        comment='accepted, presented, withdrawn'
    )
    
    data_sources = Column(JSONB, nullable=True)
    
    conference = relationship('Conference', backref='presentations')
    
    __table_args__ = (
        CheckConstraint(
            "presentation_type IN ('oral', 'poster', 'late_breaking') OR presentation_type IS NULL",
            name='check_presentation_type'
        ),
        CheckConstraint(
            "status IN ('accepted', 'presented', 'withdrawn') OR status IS NULL",
            name='check_presentation_status'
        ),
    )


class SECFiling(BaseModel):
    """SEC filing documents."""
    
    __tablename__ = 'sec_filings'
    
    filing_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    filing_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='8-K, 10-K, 10-Q, S-1, DEF 14A'
    )
    filing_date = Column(Date, nullable=False, index=True)
    accession_number = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )
    filing_url = Column(String(1000), nullable=True)
    
    mentions_programs = Column(ARRAY(Text), nullable=True)
    mentions_milestones = Column(Boolean, default=False, index=True)
    mentions_restructuring = Column(Boolean, default=False, index=True)
    
    cash_position = Column(Numeric(20, 2), nullable=True)
    runway_months = Column(Integer, nullable=True)
    
    full_text = Column(Text, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "filing_type IN ('8-K', '10-K', '10-Q', 'S-1', 'DEF 14A') OR filing_type IS NOT NULL",
            name='check_filing_type'
        ),
    )

