# src/ncfd/db/models.py
"""
Study Card Architecture - New Database Models

This module implements the complete database schema for the Study Card system,
replacing the previous architecture with a precision-first approach focused on
US-listed companies and pivotal Phase 2b/3 trials.
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List
from decimal import Decimal

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String, Text, Boolean, Date, DateTime, ForeignKey, Index,
    UniqueConstraint, Integer, BigInteger, CheckConstraint, event, func,
    PrimaryKeyConstraint, Numeric, Enum as SQLEnum, CHAR, text
)

from sqlalchemy.dialects.postgresql import ARRAY, JSONB, ENUM as PGEnum

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """SQLAlchemy declarative base for Study Card models."""
    pass

# ---------------------------------------------------------------------------
# Enums - FIXED: Instantiated instances, not classes
# ---------------------------------------------------------------------------

# PostgreSQL enums (must be instantiated, not subclassed)
ExchangeEnum = PGEnum(
    'NASDAQ', 'NYSE', 'NYSE_AM', 'OTCQX', 'OTCQB',
    name='exchange_enum', create_type=True
)
PhaseEnum = PGEnum(
    'P2', 'P2B', 'P2_3', 'P3',
    name='phase_enum', create_type=True
)
DocTypeEnum = PGEnum(
    'PR', '8K', 'Abstract', 'Poster', 'Paper', 'Registry', 'FDA',
    name='doc_type_enum', create_type=True
)
OAStatusEnum = PGEnum(
    'oa_gold', 'oa_green', 'accepted_ms', 'embargoed', 'unknown',
    name='oa_status_enum', create_type=True
)
CoverageLevelEnum = PGEnum(
    'high', 'med', 'low',
    name='coverage_level_enum', create_type=True
)
TrialStatusEnum = PGEnum(
    'Recruiting', 'Active, not recruiting', 'Completed', 'Terminated',
    'Suspended', 'Withdrawn', 'Not yet recruiting', 'Enrolling by invitation',
    'Unknown status',
    name='trial_status_enum', create_type=True
)
SeverityEnum = PGEnum(
    'H', 'M', 'L',
    name='severity_enum', create_type=True
)
SignalIDEnum = PGEnum(
    'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9',
    name='signal_id_enum', create_type=True
)
GateIDEnum = PGEnum(
    'G1', 'G2', 'G3', 'G4',
    name='gate_id_enum', create_type=True
)
CertaintyEnum = PGEnum(
    'low', 'med', 'high',
    name='certainty_enum', create_type=True
)

# SQLAlchemy enums (non-PG, don't need separate types)
RunStatusEnum = SQLEnum('success', 'failed', 'partial', name='run_status_enum')
AssignmentType = SQLEnum('sale', 'license', 'security', name='assignment_type')
ArtifactType = SQLEnum('model', 'data', 'report', 'config', name='artifact_type')
LRScopeEnum = SQLEnum('gate', 'signal', name='lr_scope')

# ---------------------------------------------------------------------------
# Reference & Identity
# ---------------------------------------------------------------------------

class Company(Base):
    """Companies table - core entity for all organizations"""
    __tablename__ = "companies"

    company_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_norm: Mapped[str] = mapped_column(Text, nullable=False)
    cik: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True)
    lei: Mapped[Optional[str]] = mapped_column(Text)
    state_incorp: Mapped[Optional[str]] = mapped_column(Text)
    country_incorp: Mapped[Optional[str]] = mapped_column(Text)
    sic: Mapped[Optional[str]] = mapped_column(Text)
    website_domain: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    aliases: Mapped[List["CompanyAlias"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    securities: Mapped[List["Security"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    assets: Mapped[List["AssetOwnership"]] = relationship(back_populates="company")
    trials: Mapped[List["Trial"]] = relationship(back_populates="sponsor_company")

    __table_args__ = (
        Index("idx_companies_website_domain", "website_domain"),
    )


class CompanyAlias(Base):
    """Company aliases and alternative names"""
    __tablename__ = "company_aliases"

    alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[Optional[date]] = mapped_column(Date)
    valid_to: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship(back_populates="aliases")

    __table_args__ = (
        Index("idx_company_aliases_company_id", "company_id"),
    )


class Security(Base):
    """Securities table - stock tickers and exchange listings"""
    __tablename__ = "securities"

    security_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    exchange: Mapped[str] = mapped_column(ExchangeEnum, nullable=False)
    is_adr: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship(back_populates="securities")

    __table_args__ = (
        Index("idx_securities_exchange", "exchange"),
        Index("idx_securities_company_id", "company_id"),
    )

# ---------------------------------------------------------------------------
# Assets & Ownership
# ---------------------------------------------------------------------------

class Asset(Base):
    """Assets table - drugs, compounds, and therapeutic agents"""
    __tablename__ = "assets"

    asset_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    names_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {inn, internal_codes[], generic[], cas, unii, chembl_id, drugbank_id}
    modality: Mapped[Optional[str]] = mapped_column(Text)
    target: Mapped[Optional[str]] = mapped_column(Text)
    moa: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    ownership: Mapped[List["AssetOwnership"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    studies: Mapped[List["Study"]] = relationship(back_populates="asset")
    patents: Mapped[List["Patent"]] = relationship(back_populates="asset")

    __table_args__ = (
        Index("idx_assets_names_jsonb", "names_jsonb", postgresql_using="gin"),
        Index("idx_assets_target", "target"),
        Index("idx_assets_moa", "moa"),
    )


class AssetOwnership(Base):
    """Asset ownership and licensing relationships"""
    __tablename__ = "asset_ownership"

    ownership_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    asset: Mapped["Asset"] = relationship(back_populates="ownership")
    company: Mapped["Company"] = relationship(back_populates="assets")

    __table_args__ = (
        Index("idx_asset_ownership_asset_id", "asset_id"),
        Index("idx_asset_ownership_company_id", "company_id"),
        Index("idx_asset_ownership_start_date", "start_date"),
    )

# ---------------------------------------------------------------------------
# Trials & Versioning
# ---------------------------------------------------------------------------

class Trial(Base):
    """Clinical trials table - core registry information"""
    __tablename__ = "trials"

    trial_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nct_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    brief_title: Mapped[Optional[str]] = mapped_column(Text)
    official_title: Mapped[Optional[str]] = mapped_column(Text)
    sponsor_text: Mapped[Optional[str]] = mapped_column(Text)
    sponsor_company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.company_id"))
    phase: Mapped[Optional[str]] = mapped_column(PhaseEnum)
    indication: Mapped[Optional[str]] = mapped_column(Text)
    is_pivotal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    primary_endpoint_text: Mapped[Optional[str]] = mapped_column(Text)
    est_primary_completion_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[Optional[str]] = mapped_column(TrialStatusEnum)
    first_posted_date: Mapped[Optional[date]] = mapped_column(Date)
    last_update_posted_date: Mapped[Optional[date]] = mapped_column(Date)
    results_first_posted_date: Mapped[Optional[date]] = mapped_column(Date)
    has_results: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lead_sponsor_class: Mapped[Optional[str]] = mapped_column(Text)
    responsible_party: Mapped[Optional[str]] = mapped_column(Text)
    allocation: Mapped[Optional[str]] = mapped_column(Text)
    masking: Mapped[Optional[str]] = mapped_column(Text)
    num_arms: Mapped[Optional[int]] = mapped_column(Integer)
    intervention_types: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # FIXED: Fixed-length hash field
    current_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sponsor_company: Mapped[Optional["Company"]] = relationship(back_populates="trials")
    versions: Mapped[List["TrialVersion"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    studies: Mapped[List["Study"]] = relationship(back_populates="trial")
    signals: Mapped[List["Signal"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    gates: Mapped[List["Gate"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    scores: Mapped[List["Score"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    catalysts: Mapped[List["Catalyst"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    labels: Mapped[List["Label"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    disclosures: Mapped[List["Disclosure"]] = relationship(back_populates="trial", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_trials_sponsor_company_id", "sponsor_company_id"),
        Index("idx_trials_est_primary_completion_date", "est_primary_completion_date"),
        Index("idx_trials_phase", "phase"),
        Index("idx_trials_status", "status"),
        Index("idx_trials_last_update_posted_date", "last_update_posted_date"),
        # ADDED: GIN index for intervention types array
        Index("idx_trials_intervention_types", "intervention_types", postgresql_using="gin"),
    )


class TrialVersion(Base):
    """Trial versioning table - tracks changes over time"""
    __tablename__ = "trial_versions"

    trial_version_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    # FIXED: Added server_default for captured_at
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # FIXED: Fixed-length hash field
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    raw_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    last_update_posted_date: Mapped[Optional[date]] = mapped_column(Date)
    primary_endpoint_text: Mapped[Optional[str]] = mapped_column(Text)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer)
    analysis_plan_text: Mapped[Optional[str]] = mapped_column(Text)
    changes_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB)
    changed_primary_endpoint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    changed_sample_size: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sample_size_delta: Mapped[Optional[int]] = mapped_column(Integer)
    changed_analysis_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    trial: Mapped["Trial"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("trial_id", "sha256", name="uq_trial_version_sha256"),
        Index("idx_trial_versions_trial_captured", "trial_id", "captured_at", postgresql_using="btree"),
    )

# ---------------------------------------------------------------------------
# Documents & Storage
# ---------------------------------------------------------------------------

class Study(Base):
    """Studies table - all documents with Study Card JSON"""
    __tablename__ = "studies"

    study_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trials.trial_id"))
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.asset_id"))
    doc_type: Mapped[str] = mapped_column(DocTypeEnum, nullable=False)
    citation: Mapped[Optional[str]] = mapped_column(Text)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    url: Mapped[Optional[str]] = mapped_column(Text)
    # FIXED: Fixed-length hash field
    hash: Mapped[Optional[str]] = mapped_column(CHAR(64))
    oa_status: Mapped[Optional[str]] = mapped_column(OAStatusEnum)
    object_store_key: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)  # Study Card JSON
    coverage_level: Mapped[str] = mapped_column(CoverageLevelEnum, nullable=False)
    notes_md: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    trial: Mapped[Optional["Trial"]] = relationship(back_populates="studies")
    asset: Mapped[Optional["Asset"]] = relationship(back_populates="studies")
    signal_evidence: Mapped[List["SignalEvidence"]] = relationship(back_populates="source_study", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_studies_trial_id", "trial_id"),
        Index("idx_studies_asset_id", "asset_id"),
        # FIXED: Partial unique index to handle NULL hashes
        Index("idx_studies_hash_unique", "hash", unique=True, postgresql_where=text("hash IS NOT NULL")),
        Index("idx_studies_extracted_jsonb", "extracted_jsonb", postgresql_using="gin"),
    )


class Disclosure(Base):
    """Optional table for crawled text bodies"""
    __tablename__ = "disclosures"

    disclosure_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(DocTypeEnum, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # FIXED: Fixed-length hash field
    text_hash: Mapped[Optional[str]] = mapped_column(CHAR(64))
    text: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    trial: Mapped["Trial"] = relationship(back_populates="disclosures")

    __table_args__ = (
        Index("idx_disclosures_trial_id", "trial_id"),
        # FIXED: Partial unique index to handle NULL hashes - fixed column reference
        Index("idx_disclosures_text_hash_unique", "text_hash", unique=True, postgresql_where=text("text_hash IS NOT NULL")),
    )

# ---------------------------------------------------------------------------
# Patents
# ---------------------------------------------------------------------------

class Patent(Base):
    """Patents table - intellectual property information"""
    __tablename__ = "patents"

    patent_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.asset_id"))
    family_id: Mapped[Optional[str]] = mapped_column(Text)
    jurisdiction: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    earliest_priority_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[Optional[str]] = mapped_column(Text)
    assignees: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    inventors: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    links_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    asset: Mapped[Optional["Asset"]] = relationship(back_populates="patents")
    assignments: Mapped[List["PatentAssignment"]] = relationship(back_populates="patent", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_patents_asset_id", "asset_id"),
        Index("idx_patents_earliest_priority_date", "earliest_priority_date"),
    )


class PatentAssignment(Base):
    """Patent assignment and licensing history"""
    __tablename__ = "patent_assignments"

    assignment_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    patent_id: Mapped[int] = mapped_column(ForeignKey("patents.patent_id", ondelete="CASCADE"), nullable=False)
    assignor: Mapped[str] = mapped_column(Text, nullable=False)
    assignee: Mapped[str] = mapped_column(Text, nullable=False)
    exec_date: Mapped[Optional[date]] = mapped_column(Date)
    record_date: Mapped[Optional[date]] = mapped_column(Date)
    type: Mapped[str] = mapped_column(AssignmentType, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    patent: Mapped["Patent"] = relationship(back_populates="assignments")

    __table_args__ = (
        Index("idx_patent_assignments_patent_id", "patent_id"),
        Index("idx_patent_assignments_exec_date", "exec_date"),
    )

# ---------------------------------------------------------------------------
# Signals → Gates → Scores - FIXED: Added run_id for lineage
# ---------------------------------------------------------------------------

class Signal(Base):
    """Signals table - primitive S1-S9 per trial"""
    __tablename__ = "signals"

    signal_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    # FIXED: Added run_id for lineage tracking
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    s_id: Mapped[str] = mapped_column(SignalIDEnum, nullable=False)
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    severity: Mapped[Optional[str]] = mapped_column(SeverityEnum)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    trial: Mapped["Trial"] = relationship(back_populates="signals")
    evidence: Mapped[List["SignalEvidence"]] = relationship(back_populates="signal", cascade="all, delete-orphan")

    __table_args__ = (
        # FIXED: Unique constraint includes run_id for lineage
        UniqueConstraint("trial_id", "s_id", "run_id", name="uq_signal_trial_sid_run"),
        Index("idx_signals_trial_sid", "trial_id", "s_id"),
        Index("idx_signals_run_id", "run_id"),
    )


class SignalEvidence(Base):
    """Signal evidence table - many evidences per signal"""
    __tablename__ = "signal_evidence"

    evidence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.signal_id", ondelete="CASCADE"), nullable=False)
    source_study_id: Mapped[Optional[int]] = mapped_column(ForeignKey("studies.study_id", ondelete="SET NULL"))
    evidence_span: Mapped[Optional[str]] = mapped_column(Text)
    metadata_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    signal: Mapped["Signal"] = relationship(back_populates="evidence")
    source_study: Mapped[Optional["Study"]] = relationship(back_populates="signal_evidence")

    __table_args__ = (
        Index("idx_signal_evidence_signal_id", "signal_id"),
        Index("idx_signal_evidence_source_study_id", "source_study_id"),
    )


class Gate(Base):
    """Gates table - composite G1-G4"""
    __tablename__ = "gates"

    # FIXED: Renamed for consistency
    gate_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    # FIXED: Added run_id for lineage tracking
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    g_id: Mapped[str] = mapped_column(GateIDEnum, nullable=False)
    fired_bool: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # FIXED: Using instance, not class
    supporting_s_ids: Mapped[List[str]] = mapped_column(ARRAY(SignalIDEnum), nullable=False)
    lr_used: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    rationale_text: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    trial: Mapped["Trial"] = relationship(back_populates="gates")

    __table_args__ = (
        # FIXED: Unique constraint includes run_id for lineage
        UniqueConstraint("trial_id", "g_id", "run_id", name="uq_gate_trial_gid_run"),
        Index("idx_gates_trial_gid", "trial_id", "g_id"),
        Index("idx_gates_run_id", "run_id"),
    )


class Score(Base):
    """Scores table - posterior probabilities per run"""
    __tablename__ = "scores"

    score_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    prior_pi: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    logit_prior: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    sum_log_lr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    logit_post: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    p_fail: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    trial: Mapped["Trial"] = relationship(back_populates="scores")

    __table_args__ = (
        Index("idx_scores_trial_id", "trial_id"),
        Index("idx_scores_run_id", "run_id"),
        Index("idx_scores_timestamp", "timestamp"),
        # ADDED: Composite index for top scores by run
        Index("idx_scores_run_pf", "run_id", "p_fail"),
        # ADDED: CHECK constraints for probability ranges
        CheckConstraint("prior_pi BETWEEN 0 AND 1", name="ck_scores_prior_pi_01"),
        CheckConstraint("p_fail BETWEEN 0 AND 1", name="ck_scores_p_fail_01"),
        CheckConstraint("logit_post BETWEEN -50 AND 50", name="ck_scores_logit_post_range"),
    )


class LRTable(Base):
    """Likelihood ratio tables - configurable calibration per gate/universe"""
    __tablename__ = "lr_tables"

    lr_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(LRScopeEnum, nullable=False)
    id_code: Mapped[str] = mapped_column(Text, nullable=False)
    universe_tag: Mapped[str] = mapped_column(Text, nullable=False)
    lr_value: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    ci_low: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    ci_high: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_lr_tables_id_universe_effective", "id_code", "universe_tag", "effective_from"),
    )

# ---------------------------------------------------------------------------
# Catalyst Timing & Evaluation
# ---------------------------------------------------------------------------

class Catalyst(Base):
    """Catalysts table - timing windows for trial readouts"""
    __tablename__ = "catalysts"

    catalyst_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    certainty: Mapped[str] = mapped_column(CertaintyEnum, nullable=False)
    sources: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    trial: Mapped["Trial"] = relationship(back_populates="catalysts")

    __table_args__ = (
        Index("idx_catalysts_trial_id", "trial_id"),
        Index("idx_catalysts_window_start", "window_start"),
        # ADDED: CHECK constraint for window order
        CheckConstraint("window_end >= window_start", name="ck_catalyst_window_order"),
    )


class Label(Base):
    """Labels table - ground truth for backtests"""
    __tablename__ = "labels"

    label_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    primary_outcome_success_bool: Mapped[bool] = mapped_column(Boolean, nullable=False)
    price_move_5d: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    label_source_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    trial: Mapped["Trial"] = relationship(back_populates="labels")

    __table_args__ = (
        Index("idx_labels_trial_id", "trial_id"),
        Index("idx_labels_event_date", "event_date"),
    )


class Market(Base):
    """Markets table - optional market data for analysis"""
    __tablename__ = "markets"

    mkt_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    market_cap: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_markets_ticker_date", "ticker", "date"),
    )

# ---------------------------------------------------------------------------
# Run Lineage & Operations
# ---------------------------------------------------------------------------

class Run(Base):
    """Runs table - execution lineage tracking"""
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(RunStatusEnum, nullable=False)
    flow_name: Mapped[str] = mapped_column(Text, nullable=False)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    artifacts: Mapped[List["RunArtifact"]] = relationship(back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_runs_started_at", "started_at"),
        Index("idx_runs_status", "status"),
        Index("idx_runs_flow_name", "flow_name"),
    )


class RunArtifact(Base):
    """Run artifacts table - output tracking per run"""
    __tablename__ = "run_artifacts"

    artifact_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(ArtifactType, nullable=False)
    object_store_key: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    run: Mapped["Run"] = relationship(back_populates="artifacts")

    __table_args__ = (
        Index("idx_run_artifacts_run_id", "run_id"),
        Index("idx_run_artifacts_type", "artifact_type"),
    )
