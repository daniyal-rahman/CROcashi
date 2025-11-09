"""
Entity resolution and matching models.
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


class EntityAlias(BaseModel):
    """Entity aliases for matching."""
    
    __tablename__ = 'entity_aliases'
    
    alias_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    entity_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='company, drug, disease, target, institution'
    )
    entity_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment='References the actual entity'
    )
    alias_text = Column(
        String(500),
        nullable=False,
        index=True
    )
    alias_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment='former_name, code_name, brand_name, abbreviation, misspelling'
    )
    source = Column(String(200), nullable=True)
    confidence_score = Column(
        Numeric(3, 2),
        nullable=True,
        comment='0-1 confidence score'
    )
    valid_from = Column(
        Date,
        nullable=True,
        index=True,
        comment='When this alias became valid'
    )
    valid_to = Column(
        Date,
        nullable=True,
        index=True,
        comment='When this alias stopped being valid (NULL = still valid)'
    )
    
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('company', 'drug', 'disease', 'target', 'institution', 'trial', 'publication', 'patent')",
            name='check_entity_type_alias'
        ),
        CheckConstraint(
            "alias_type IN ('former_name', 'code_name', 'brand_name', 'abbreviation', 'misspelling', 'original_name', 'manual_review') OR alias_type IS NULL",
            name='check_alias_type'
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name='check_confidence_score'
        ),
        {'comment': 'Entity aliases table with indexes for fast lookups'}
    )


class EntityMatch(BaseModel):
    """Entity matches across sources."""
    
    __tablename__ = 'entity_matches'
    
    match_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    entity_type = Column(
        String(50),
        nullable=False,
        index=True
    )
    source_1 = Column(String(200), nullable=True)
    source_1_id = Column(String(200), nullable=True)
    source_2 = Column(String(200), nullable=True)
    source_2_id = Column(String(200), nullable=True)
    
    matched_entity_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True
    )
    match_confidence = Column(
        Numeric(3, 2),
        nullable=True,
        comment='0-1 confidence score'
    )
    match_method = Column(
        String(50),
        nullable=True,
        index=True,
        comment='exact_match, fuzzy_match, structural_match, llm_match, manual'
    )
    verified = Column(Boolean, default=False, index=True)
    
    __table_args__ = (
        CheckConstraint(
            "match_confidence >= 0 AND match_confidence <= 1",
            name='check_match_confidence'
        ),
        CheckConstraint(
            "match_method IN ('exact_match', 'fuzzy_match', 'structural_match', 'llm_match', 'manual') OR match_method IS NULL",
            name='check_match_method'
        ),
    )


class EntityMatchConfidence(BaseModel):
    """Entity match confidence with review tracking."""
    
    __tablename__ = 'entity_match_confidence'
    
    match_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    entity_type = Column(
        String(50),
        nullable=False,
        index=True
    )
    source_text = Column(String(500), nullable=False, index=True)
    source_system = Column(String(200), nullable=True, index=True)
    source_record_id = Column(String(200), nullable=True)
    
    matched_entity_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True
    )
    confidence_score = Column(
        Numeric(3, 2),
        nullable=True,
        index=True,
        comment='0-1 confidence score'
    )
    matching_method = Column(String(50), nullable=True)
    
    needs_review = Column(Boolean, default=False, index=True)
    reviewed_by = Column(String(200), nullable=True)
    reviewed_at = Column(Date, nullable=True)
    review_status = Column(
        String(50),
        nullable=True,
        index=True,
        comment='confirmed, corrected, ambiguous'
    )
    
    original_matched_entity_id = Column(UUID(as_uuid=True), nullable=True)
    corrected_matched_entity_id = Column(UUID(as_uuid=True), nullable=True)
    correction_reason = Column(Text, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name='check_match_confidence_score'
        ),
        CheckConstraint(
            "review_status IN ('confirmed', 'corrected', 'ambiguous') OR review_status IS NULL",
            name='check_review_status'
        ),
    )


class MatchingReviewQueue(BaseModel):
    """Queue for manual matching review."""
    
    __tablename__ = 'matching_review_queue'
    
    queue_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    entity_type = Column(
        String(50),
        nullable=False,
        index=True
    )
    source_text = Column(String(500), nullable=False, index=True)
    source_context = Column(JSONB, nullable=True)
    
    candidate_matches = Column(
        JSONB,
        nullable=True,
        comment='Array of {entity_id, name, score}'
    )
    
    priority = Column(
        String(20),
        nullable=False,
        default='medium',
        index=True,
        comment='high, medium, low'
    )
    assigned_to = Column(String(200), nullable=True, index=True)
    status = Column(
        String(50),
        nullable=False,
        default='pending',
        index=True,
        comment='pending, in_review, resolved, needs_more_info'
    )
    
    resolution = Column(JSONB, nullable=True)
    resolved_at = Column(Date, nullable=True, index=True)
    
    __table_args__ = (
        CheckConstraint(
            "priority IN ('high', 'medium', 'low')",
            name='check_priority'
        ),
        CheckConstraint(
            "status IN ('pending', 'in_review', 'resolved', 'needs_more_info')",
            name='check_queue_status'
        ),
    )


class EntityMatchCandidate(BaseModel):
    """Entity match candidates for resolution pipeline."""
    
    __tablename__ = 'entity_match_candidates'
    
    candidate_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    entity_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='company, drug, disease, target, trial, publication'
    )
    source_identifier = Column(
        String(500),
        nullable=False,
        index=True,
        comment='e.g., NCT number, PMID, accession number'
    )
    source_name = Column(
        String(200),
        nullable=False,
        index=True,
        comment='ClinicalTrials.gov, PubMed, FDA, SEC'
    )
    extracted_text = Column(
        String(1000),
        nullable=False,
        comment='The name/text extracted from source'
    )
    extracted_context = Column(
        JSONB,
        nullable=True,
        comment='Additional context for matching'
    )
    
    # Potential matches found by algorithm
    potential_matches = Column(
        JSONB,
        nullable=True,
        comment='Array of {"entity_id": "...", "score": 0.85, "reason": "..."}'
    )
    
    # Resolution decision
    matched_to = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment='Final canonical entity_id'
    )
    match_confidence = Column(
        Numeric(3, 2),
        nullable=True,
        comment='0.0 to 1.0'
    )
    match_method = Column(
        String(50),
        nullable=True,
        index=True,
        comment='exact_identifier, exact_name, alias, fuzzy_context, manual'
    )
    match_reasoning = Column(
        Text,
        nullable=True,
        comment='Explanation of why this match was made'
    )
    
    # Review tracking
    status = Column(
        String(50),
        nullable=False,
        default='pending',
        index=True,
        comment='pending, auto_matched, needs_review, reviewed, new_entity'
    )
    reviewed_by = Column(String(200), nullable=True)
    reviewed_at = Column(Date, nullable=True, index=True)
    review_notes = Column(Text, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('company', 'drug', 'disease', 'target', 'trial', 'publication', 'institution')",
            name='check_candidate_entity_type'
        ),
        CheckConstraint(
            "status IN ('pending', 'auto_matched', 'needs_review', 'reviewed', 'new_entity')",
            name='check_candidate_status'
        ),
        CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name='check_candidate_confidence'
        ),
        {'comment': 'Entity match candidates for resolution pipeline'}
    )


class EntityMatchingRule(BaseModel):
    """Configurable entity matching rules and strategies."""
    
    __tablename__ = 'entity_matching_rules'
    
    rule_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    entity_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment='company, drug, disease, target, trial'
    )
    matching_strategy = Column(
        String(50),
        nullable=False,
        index=True,
        comment='exact_identifier, exact_name, fuzzy_name, context_aware, alias'
    )
    priority = Column(
        Integer,
        nullable=False,
        index=True,
        comment='Order to try strategies (1 = highest priority)'
    )
    
    # Configuration for this strategy
    config = Column(
        JSONB,
        nullable=True,
        comment='e.g., {"threshold": 0.85, "use_context": true, "context_weight": 0.3}'
    )
    
    active = Column(Boolean, default=True, index=True)
    last_modified = Column(Date, nullable=True)
    
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('company', 'drug', 'disease', 'target', 'trial', 'publication', 'institution')",
            name='check_rule_entity_type'
        ),
        CheckConstraint(
            "matching_strategy IN ('exact_identifier', 'exact_name', 'fuzzy_name', 'context_aware', 'alias')",
            name='check_matching_strategy'
        ),
        {'comment': 'Configurable entity matching rules'}
    )


class SourceProcessingLog(BaseModel):
    """Processing log for source data."""
    
    __tablename__ = 'source_processing_log'
    
    log_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    source_name = Column(
        String(200),
        nullable=False,
        index=True,
        comment='clinicaltrials_gov, fda_drugs, sec_edgar, pubmed'
    )
    source_identifier = Column(
        String(500),
        nullable=False,
        index=True,
        comment='Specific record ID (NCT#, PMID, etc.)'
    )
    processing_started_at = Column(
        Date,
        nullable=False,
        index=True
    )
    processing_completed_at = Column(Date, nullable=True, index=True)
    processing_status = Column(
        String(50),
        nullable=False,
        default='processing',
        index=True,
        comment='success, partial, failed, needs_review'
    )
    
    # Metrics
    entities_extracted = Column(Integer, nullable=True)
    entities_matched = Column(Integer, nullable=True)
    entities_created = Column(Integer, nullable=True)
    relationships_created = Column(Integer, nullable=True)
    
    # Issues
    warnings = Column(ARRAY(Text), nullable=True)
    errors = Column(ARRAY(Text), nullable=True)
    
    # Detailed log
    processing_details = Column(
        JSONB,
        nullable=True,
        comment='Detailed processing information'
    )
    
    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('processing', 'success', 'partial', 'failed', 'needs_review')",
            name='check_processing_status'
        ),
        {'comment': 'Source processing audit log'}
    )


class DataQualityMetric(BaseModel):
    """Data quality metrics and statistics."""
    
    __tablename__ = 'data_quality_metrics'
    
    metric_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    metric_date = Column(
        Date,
        nullable=False,
        index=True
    )
    entity_type = Column(
        String(50),
        nullable=False,
        index=True
    )
    
    total_entities = Column(Integer, nullable=True)
    entities_with_multiple_sources = Column(Integer, nullable=True)
    entities_with_single_source = Column(Integer, nullable=True)
    
    high_confidence_matches = Column(Integer, nullable=True)
    medium_confidence_matches = Column(Integer, nullable=True)
    low_confidence_matches = Column(Integer, nullable=True)
    
    pending_manual_review = Column(Integer, nullable=True)
    
    companies_with_drugs = Column(Integer, nullable=True)
    companies_without_drugs = Column(Integer, nullable=True)
    
    drugs_with_trials = Column(Integer, nullable=True)
    drugs_without_trials = Column(Integer, nullable=True)
    
    trials_with_publications = Column(Integer, nullable=True)
    trials_without_publications = Column(Integer, nullable=True)

