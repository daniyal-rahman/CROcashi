"""
Study Card Database Models

SQLAlchemy ORM models for study card related tables.
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


class MethodCard(Base):
    """SQLAlchemy model for method_cards table."""
    __tablename__ = 'method_cards'
    
    id = Column(Integer, primary_key=True)
    doc_id = Column(String, nullable=False)
    design_archetype = Column(String, nullable=True)
    is_blinded = Column(Boolean, nullable=True)
    analysis_set = Column(String, nullable=True)
    population_description = Column(Text, nullable=True)
    stratification_factors = Column(JSON, nullable=True)
    covariate_adjustment = Column(JSON, nullable=True)
    primary_endpoint = Column(Text, nullable=True)
    secondary_endpoints = Column(JSON, nullable=True)
    summary_measure = Column(String, nullable=True)
    alpha_level = Column(Float, nullable=True)
    is_one_sided = Column(Boolean, nullable=True)
    multiplicity_adjustment = Column(String, nullable=True)
    sample_size_reassessment = Column(Boolean, nullable=True)
    interim_looks = Column(JSON, nullable=True)
    interim_timing = Column(String, nullable=True)
    spending_function = Column(String, nullable=True)
    stop_rules = Column(JSON, nullable=True)
    missingness_assumption = Column(String, nullable=True)
    missingness_pattern = Column(String, nullable=True)
    imputation_method = Column(String, nullable=True)
    estimand = Column(Text, nullable=True)
    intercurrent_events_policy = Column(Text, nullable=True)
    endpoint_ascertainment = Column(String, nullable=True)
    assessment_interval = Column(String, nullable=True)
    adjudication_committee = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ResultsFactsheet(Base):
    """SQLAlchemy model for results_factsheets table."""
    __tablename__ = 'results_factsheets'
    
    id = Column(Integer, primary_key=True)
    doc_id = Column(String, nullable=False)
    results = Column(JSON, nullable=True)
    primary_endpoint_results = Column(JSON, nullable=True)
    secondary_endpoint_results = Column(JSON, nullable=True)
    safety_results = Column(JSON, nullable=True)
    primary_analysis_set = Column(String, nullable=True)
    secondary_analysis_sets = Column(JSON, nullable=True)
    total_enrolled = Column(Integer, nullable=True)
    completed_primary_endpoint = Column(Integer, nullable=True)
    dropout_rate = Column(Float, nullable=True)
    follow_up_completion = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class GateAssessment(Base):
    """SQLAlchemy model for gate_assessments table."""
    __tablename__ = 'gate_assessments'
    
    id = Column(Integer, primary_key=True)
    gate_id = Column(String, nullable=False)
    status = Column(String, nullable=False)
    p_gate = Column(Float, nullable=True)
    rationale = Column(JSON, nullable=True)
    sensitivity = Column(JSON, nullable=True)
    computed_values = Column(JSON, nullable=True)
    threshold_comparisons = Column(JSON, nullable=True)
    assessment_method = Column(String, nullable=True)
    confidence_in_assessment = Column(Float, nullable=True)
    assessment_notes = Column(JSON, nullable=True)
    next_steps = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class EvidenceSpan(Base):
    """SQLAlchemy model for evidence_spans table."""
    __tablename__ = 'evidence_spans'
    
    id = Column(Integer, primary_key=True)
    doc_id = Column(String, nullable=False)
    quote = Column(Text, nullable=False)
    section = Column(String, nullable=False)
    page = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)
    table_id = Column(String, nullable=True)
    table_row = Column(Integer, nullable=True)
    table_col = Column(Integer, nullable=True)
    table_header_ids = Column(JSON, nullable=True)
    figure_id = Column(String, nullable=True)
    supplementary_id = Column(String, nullable=True)
    kind = Column(String, nullable=True)
    parent_span_ids = Column(JSON, nullable=True)
    internal_id = Column(String, nullable=True)
    status = Column(String, nullable=True)
    span_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
