# src/ncfd/db/models.py
"""
Study Card Architecture - New Database Models

Precision-first schema for US-listed issuers and pivotal Phase 2b/3 trials.
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any

# import sqlalchemy as sa
from sqlalchemy import (String, Text, Boolean, Date, DateTime, Float, ForeignKey, Index, UniqueConstraint, Integer, BigInteger, CheckConstraint, func, Numeric, Enum as SQLEnum, CHAR, text, MetaData, PrimaryKeyConstraint, ForeignKeyConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, ENUM as PGEnum


# ---------------------------------------------------------------------------
# Base with naming convention
# ---------------------------------------------------------------------------

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_N_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ---------------------------------------------------------------------------
# Enums (Postgres types will be created in baseline)
# ---------------------------------------------------------------------------

PhaseEnum = PGEnum(
    "PHASE1", "PHASE2", "PHASE3", "PHASE4",
    "PHASE2_PHASE3", "PHASE1_PHASE2", "PHASE3_PHASE4",
    "EARLY_PHASE1",
    name="phase_enum", create_type=True
)
DocTypeEnum = PGEnum(
    "pr", "8k", "abstract", "poster", "paper", "registry", "fda", name="doc_type_enum", create_type=True
)
OAStatusEnum = PGEnum(
    "oa_gold", "oa_green", "accepted_ms", "embargoed", "unknown", name="oa_status_enum", create_type=True
)
CoverageLevelEnum = PGEnum("high", "med", "low", name="coverage_level_enum", create_type=True)
TrialStatusEnum = PGEnum(
    "recruiting",
    "active_not_recruiting",
    "completed",
    "terminated",
    "suspended",
    "withdrawn",
    "not_yet_recruiting",
    "enrolling_by_invitation",
    "unknown_status",
    name="trial_status_enum",
    create_type=True,
)
SeverityEnum = PGEnum("H", "M", "L", name="severity_enum", create_type=True)
SignalIDEnum = PGEnum("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", name="signal_id_enum", create_type=True)
GateIDEnum = PGEnum("G1", "G2", "G3", "G4", name="gate_id_enum", create_type=True)
CertaintyEnum = PGEnum("low", "med", "high", name="certainty_enum", create_type=True)

# App-level (not PG) enums
RunStatusEnum = SQLEnum("success", "failed", "partial", name="run_status_enum")
AssignmentType = SQLEnum("sale", "license", "security", name="assignment_type")
ArtifactType = SQLEnum("model", "data", "report", "config", name="artifact_type")


# ---------------------------------------------------------------------------
# Reference & Identity
# ---------------------------------------------------------------------------

class Company(Base):
    __tablename__ = "companies"

    company_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_norm: Mapped[str] = mapped_column(Text, nullable=False)
    # CIK must preserve leading zeros
    cik: Mapped[Optional[str]] = mapped_column(CHAR(10), unique=True)
    lei: Mapped[Optional[str]] = mapped_column(Text)
    state_incorp: Mapped[Optional[str]] = mapped_column(Text)
    country_incorp: Mapped[Optional[str]] = mapped_column(Text)
    sic: Mapped[Optional[str]] = mapped_column(Text)
    website_domain: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    securities: Mapped[List["Security"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    owned_assets: Mapped[List["Asset"]] = relationship("Asset", foreign_keys="Asset.owner_company_id")
    trials: Mapped[List["Trial"]] = relationship(back_populates="sponsor_company")

    __table_args__ = (
        Index("idx_companies_website_domain", "website_domain"),
        # trigram GIN (requires pg_trgm extension)
        Index(
            "idx_companies_name_norm",
            text("name_norm gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )


class CompanyAlias(Base):
    """Company aliases for fuzzy matching."""
    __tablename__ = "company_aliases"

    alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    alias_norm: Mapped[str] = mapped_column(Text, nullable=False)
    alias_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship("Company", foreign_keys=[company_id])

    __table_args__ = (
        Index("idx_company_aliases_company_id", "company_id"),
        Index("idx_company_aliases_alias_norm", "alias_norm"),
        Index("idx_company_aliases_alias_type", "alias_type"),
        CheckConstraint("alias_type IN ('legal','aka','former_name','short','subsidiary','brand','domain')", name='ck_company_aliases_alias_type_valid'),
    )


class Security(Base):
    __tablename__ = "securities"

    security_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    exchange_id: Mapped[int] = mapped_column(Integer, ForeignKey("exchanges.exchange_id"), nullable=False)
    is_adr: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company: Mapped["Company"] = relationship(back_populates="securities")
    exchange: Mapped["Exchange"] = relationship(back_populates="securities")

    __table_args__ = (
        Index("idx_securities_exchange_id", "exchange_id"),
        Index("idx_securities_company_id", "company_id"),
        Index("idx_securities_active", "active"),
    )


# ---------------------------------------------------------------------------
# Exchange Lookup
# ---------------------------------------------------------------------------

class Exchange(Base):
    """Exchange lookup table."""
    __tablename__ = "exchanges"
    
    exchange_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    
    # Relationships
    securities: Mapped[List["Security"]] = relationship(back_populates="exchange")
    
    __table_args__ = (
        Index("idx_exchanges_code", "code"),
    )


# ---------------------------------------------------------------------------
# Assets & Ownership
# ---------------------------------------------------------------------------

class Asset(Base):
    __tablename__ = "assets"

    asset_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    names: Mapped[Dict[str, object]] = mapped_column(JSONB, nullable=False)  # {canonical: str, aliases: [str], sources: [{alias, source, first_seen}]}
    modality: Mapped[Optional[str]] = mapped_column(Text)
    target: Mapped[Optional[str]] = mapped_column(Text)
    moa: Mapped[Optional[str]] = mapped_column(Text)
    
    # Simplified ownership (one-to-one)
    owner_company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.company_id"))
    ownership_history: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Relationships
    owner_company: Mapped[Optional["Company"]] = relationship("Company", foreign_keys=[owner_company_id], overlaps="owned_assets")
    studies: Mapped[List["Study"]] = relationship(back_populates="asset")
    patents: Mapped[List["Patent"]] = relationship(back_populates="asset")

    __table_args__ = (
        Index("idx_assets_names", "names", postgresql_using="gin"),
        Index("idx_assets_target", "target"),
        Index("idx_assets_moa", "moa"),
        Index("ix_assets_owner_company_id", "owner_company_id"),
    )




# ---------------------------------------------------------------------------
# Trials & Versioning
# ---------------------------------------------------------------------------

class Trial(Base):
    __tablename__ = "trials"

    trial_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nct_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    brief_title: Mapped[Optional[str]] = mapped_column(Text)
    official_title: Mapped[Optional[str]] = mapped_column(Text)
    sponsor_text: Mapped[Optional[str]] = mapped_column(Text)
    sponsor_company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.company_id"))
    # phase: Mapped[Optional[str]] = mapped_column(PhaseEnum)
    # DB: VARCHAR(8) with CHECK (P2, P2B, P2/3, P3)
    phase: Mapped[Optional[str]] = mapped_column(String(8))
    indication: Mapped[Optional[str]] = mapped_column(Text)
    is_pivotal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    primary_endpoint_text: Mapped[Optional[str]] = mapped_column(Text)
    est_primary_completion_date: Mapped[Optional[date]] = mapped_column(Date)
    # status: Mapped[Optional[str]] = mapped_column(TrialStatusEnum)
    # DB: VARCHAR(40) (ALL CAPS per your CHECK)
    status: Mapped[Optional[str]] = mapped_column(String(40))
    first_posted_date: Mapped[Optional[date]] = mapped_column(Date)
    last_update_posted_date: Mapped[Optional[date]] = mapped_column(Date)
    results_first_posted_date: Mapped[Optional[date]] = mapped_column(Date)
    has_results: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    lead_sponsor_class: Mapped[Optional[str]] = mapped_column(Text)
    responsible_party: Mapped[Optional[str]] = mapped_column(Text)
    allocation: Mapped[Optional[str]] = mapped_column(Text)
    masking: Mapped[Optional[str]] = mapped_column(Text)
    num_arms: Mapped[Optional[int]] = mapped_column(Integer)
    intervention_types: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    current_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sponsor_company: Mapped[Optional["Company"]] = relationship(back_populates="trials")
    versions: Mapped[List["TrialVersion"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    studies: Mapped[List["Study"]] = relationship(back_populates="trial")
    signals: Mapped[List["Signal"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    gates: Mapped[List["Gate"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    scores: Mapped[List["Score"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    catalysts: Mapped[List["Catalyst"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    labels: Mapped[List["Label"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    disclosures: Mapped[List["Disclosure"]] = relationship(back_populates="trial", cascade="all, delete-orphan")
    
    # Documents relationship (simplified system) - using DocumentManager instead of ORM relationship
    # documents: Mapped[List["Document"]] = relationship(back_populates="trial")

    __table_args__ = (
        Index("idx_trials_sponsor_company_id", "sponsor_company_id"),
        Index("idx_trials_est_primary_completion_date", "est_primary_completion_date"),
        Index("idx_trials_phase", "phase"),
        Index("idx_trials_status", "status"),
        Index("idx_trials_last_update_posted_date", "last_update_posted_date"),
        Index("idx_trials_intervention_types", "intervention_types", postgresql_using="gin"),
        Index("idx_trials_current_sha256", "current_sha256"),
    )


# EntityPack is now generated at runtime from existing database tables
# No database model needed - see EntityPackManager in orchestrator.py


class TrialVersion(Base):
    __tablename__ = "trial_versions"

    trial_version_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    raw_jsonb: Mapped[Dict[str, object]] = mapped_column(JSONB, nullable=False)
    last_update_posted_date: Mapped[Optional[date]] = mapped_column(Date)
    primary_endpoint_text: Mapped[Optional[str]] = mapped_column(Text)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer)
    analysis_plan_text: Mapped[Optional[str]] = mapped_column(Text)
    changes: Mapped[Optional[Dict[str, object]]] = mapped_column(JSONB)
    changed_primary_endpoint: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    changed_sample_size: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sample_size_delta: Mapped[Optional[int]] = mapped_column(Integer)
    changed_analysis_plan: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    meta: Mapped[Optional[Dict[str, object]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    trial: Mapped["Trial"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("trial_id", "sha256", name="uq_trial_version_sha256"),
        Index("idx_trial_versions_trial_captured", "trial_id", "captured_at", postgresql_using="btree"),
    )


# ---------------------------------------------------------------------------
# Documents & Storage
# ---------------------------------------------------------------------------

class Study(Base):
    __tablename__ = "studies"

    study_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"))
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.asset_id", ondelete="SET NULL"))
    doc_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.doc_id", ondelete="SET NULL"))
    doc_type: Mapped[str] = mapped_column(DocTypeEnum, nullable=False)
    citation: Mapped[Optional[str]] = mapped_column(Text)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    url: Mapped[Optional[str]] = mapped_column(Text)
    text_hash: Mapped[Optional[str]] = mapped_column(CHAR(64))
    oa_status: Mapped[Optional[str]] = mapped_column(OAStatusEnum)
    object_store_key: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_data: Mapped[Dict[str, object]] = mapped_column(JSONB, nullable=False)
    coverage_level: Mapped[str] = mapped_column(CoverageLevelEnum, nullable=False)
    notes_md: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    trial: Mapped[Optional["Trial"]] = relationship(back_populates="studies")
    asset: Mapped[Optional["Asset"]] = relationship(back_populates="studies")
    signal_evidence: Mapped[List["SignalEvidence"]] = relationship(
        back_populates="source_study", cascade="all, delete-orphan"
    )
    # Documents are linked through DocumentLink table
    # documents: Mapped[List["Document"]] = relationship(back_populates="trials")

    __table_args__ = (
        Index("idx_studies_trial_id", "trial_id"),
        Index("idx_studies_asset_id", "asset_id"),
        Index("idx_studies_doc_id", "doc_id"),
        Index("idx_studies_doc_type", "doc_type"),
        Index("idx_studies_text_hash_unique", "text_hash", unique=True, postgresql_where=text("text_hash IS NOT NULL")),
        Index("idx_studies_extracted_data", "extracted_data", postgresql_using="gin"),
        UniqueConstraint("object_store_key", name="uq_studies_object_store_key"),
    )


class Disclosure(Base):
    __tablename__ = "disclosures"

    disclosure_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(DocTypeEnum, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    text_hash: Mapped[Optional[str]] = mapped_column(CHAR(64))
    text: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    trial: Mapped["Trial"] = relationship(back_populates="disclosures")

    __table_args__ = (
        Index("idx_disclosures_trial_id", "trial_id"),
        Index("idx_disclosures_text_hash_unique", "text_hash", unique=True, postgresql_where=Text("text_hash IS NOT NULL")),
        UniqueConstraint("trial_id", "url", name="uq_disclosures_trial_url"),
    )


# ---------------------------------------------------------------------------
# Patents
# ---------------------------------------------------------------------------

class Patent(Base):
    __tablename__ = "patents"

    patent_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.asset_id", ondelete="SET NULL"))
    family_id: Mapped[Optional[str]] = mapped_column(Text)
    jurisdiction: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[str] = mapped_column(Text, nullable=False)
    earliest_priority_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[Optional[str]] = mapped_column(Text)
    assignees: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    inventors: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    links: Mapped[Optional[Dict[str, object]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset: Mapped[Optional["Asset"]] = relationship(back_populates="patents")
    assignments: Mapped[List["PatentAssignment"]] = relationship(back_populates="patent", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_patents_asset_id", "asset_id"),
        Index("idx_patents_earliest_priority_date", "earliest_priority_date"),
        UniqueConstraint("jurisdiction", "number", name="uq_patents_jurisdiction_number"),
    )


class PatentAssignment(Base):
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

    patent: Mapped["Patent"] = relationship(back_populates="assignments")

    __table_args__ = (
        Index("idx_patent_assignments_patent_id", "patent_id"),
        Index("idx_patent_assignments_exec_date", "exec_date"),
    )


# ---------------------------------------------------------------------------
# Signals → Gates → Scores
# ---------------------------------------------------------------------------

class Signal(Base):
    __tablename__ = "signals"

    signal_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False)
    s_id: Mapped[str] = mapped_column(SignalIDEnum, nullable=False)
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    severity: Mapped[Optional[str]] = mapped_column(SeverityEnum)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    meta: Mapped[Optional[Dict[str, object]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    trial: Mapped["Trial"] = relationship(back_populates="signals")
    evidence: Mapped[List["SignalEvidence"]] = relationship(back_populates="signal", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("trial_id", "s_id", "run_id", name="uq_signal_trial_sid_run"),
        Index("idx_signals_trial_sid", "trial_id", "s_id"),
        Index("idx_signals_run_id", "run_id"),
    )


class SignalEvidence(Base):
    __tablename__ = "signal_evidence"

    evidence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.signal_id", ondelete="CASCADE"), nullable=False)
    source_study_id: Mapped[Optional[int]] = mapped_column(ForeignKey("studies.study_id", ondelete="SET NULL"))
    evidence_span: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[Dict]] = mapped_column(JSONB)
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


class GateAssessment(Base):
    """SQLAlchemy model for gate_assessments table."""
    __tablename__ = 'gate_assessments'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gate_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    p_gate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rationale: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    sensitivity: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    computed_values: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    threshold_comparisons: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    assessment_method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence_in_assessment: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assessment_notes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    next_steps: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_gate_assessments_gate_id", "gate_id"),
        Index("idx_gate_assessments_status", "status"),
        Index("idx_gate_assessments_created_at", "created_at"),
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


# ---------------------------------------------------------------------------
# Document Staging & Literature
# ---------------------------------------------------------------------------

class Document(Base):
    """Documents table - raw document metadata and status tracking."""
    __tablename__ = "documents"

    doc_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    parsed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pmid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pmcid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nct_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sponsor_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default='discovered')
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    storage_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processing_stage: Mapped[str] = mapped_column(String(20), nullable=False, server_default='raw')
    
    # R/S Scoring fields (folded from doc_rs_scores table)
    r_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5,4), nullable=True)
    r_tier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    s_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5,4), nullable=True)
    s_tier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    r_components: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    s_components: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    rs_decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Trial association fields (simplified system)
    trial_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default='discovered')
    processing_priority: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    retrieval_tier: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    link_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(3,2), nullable=True)
    scored_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    selected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    study_card_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    text: Mapped[Optional["DocumentText"]] = relationship(back_populates="document", uselist=False, cascade="all, delete-orphan")
    tables: Mapped[List["DocumentTable"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    citations: Mapped[List["DocumentCitation"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    entities: Mapped[List["DocumentEntity"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    spans: Mapped[List["Span"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    pubmed_meta: Mapped[Optional["PubMedMeta"]] = relationship(back_populates="document", uselist=False, cascade="all, delete-orphan")
    pmc_meta: Mapped[Optional["PmcMeta"]] = relationship(back_populates="document", uselist=False, cascade="all, delete-orphan")
    
    # Trial relationship (simplified system) - using DocumentManager instead of ORM relationship
    # trial: Mapped[Optional["Trial"]] = relationship(back_populates="documents", foreign_keys=[trial_id])

    __table_args__ = (
        Index("ix_documents_lower_doi", "doi"),
        Index("ix_documents_lower_pmid", "pmid"),
        Index("ix_documents_lower_pmcid", "pmcid"),
        Index("ix_documents_lower_nct_id", "nct_id"),
        Index("ix_documents_published_at", "published_at"),
        Index("ix_documents_url_hash", "url_hash", unique=True),
        Index("ix_documents_sha256", "sha256"),
        Index("ix_documents_source_url", "source_url"),
        Index("ix_documents_processing_stage", "processing_stage"),
        Index("ix_documents_r_tier", "r_tier"),
        Index("ix_documents_s_tier", "s_tier"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_trial_id", "trial_id"),
        Index("ix_documents_processing_status", "processing_status"),
        Index("ix_documents_processing_priority", "processing_priority"),
        Index("ix_documents_retrieval_tier", "retrieval_tier"),
        CheckConstraint("source_type::text = ANY (ARRAY['PR','IR','SEC','Registry','Abstract','Poster','Paper','FDA','Patent']::text[])", name='ck_documents_source_type'),
        CheckConstraint("status::text = ANY (ARRAY['discovered','fetched','parsed','linked','failed']::text[])", name='ck_documents_status'),
        CheckConstraint("processing_stage::text = ANY (ARRAY['raw'::text, 'processed'::text])", name='ck_documents_processing_stage'),
        CheckConstraint("r_score IS NULL OR (r_score >= 0 AND r_score <= 1)", name='ck_documents_r_score_range'),
        CheckConstraint("s_score IS NULL OR (s_score >= 0 AND s_score <= 1)", name='ck_documents_s_score_range'),
        CheckConstraint("r_tier IS NULL OR r_tier IN ('R0','R1','R2','R3')", name='ck_documents_r_tier'),
        CheckConstraint("s_tier IS NULL OR s_tier IN ('S0','S1','S2','S3')", name='ck_documents_s_tier'),
        CheckConstraint("processing_status::text = ANY (ARRAY['discovered','scored','selected','processed','study_card_generated']::text[])", name='ck_documents_processing_status'),
        CheckConstraint("processing_priority::text = ANY (ARRAY['HIGH','MEDIUM','LOW','FALLBACK']::text[])", name='ck_documents_processing_priority'),
        CheckConstraint("retrieval_tier::text = ANY (ARRAY['A','B','C','D','E']::text[])", name='ck_documents_retrieval_tier'),
        CheckConstraint("link_confidence IS NULL OR (link_confidence >= 0 AND link_confidence <= 1)", name='ck_documents_link_confidence_range')
    )


class DocumentText(Base):
    """Document text table - abstracts and full text content."""
    __tablename__ = "document_text"

    doc_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    abstract_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fulltext_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fulltext_ttl_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    char_count_abstract: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_count_fulltext: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="text")

    __table_args__ = (
        ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
    )




class DocumentTable(Base):
    """Document tables table - extracted table data."""
    __tablename__ = "document_tables"

    doc_id: Mapped[int] = mapped_column(Integer, nullable=False)
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    table_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    table_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    detector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="tables")

    __table_args__ = (
        PrimaryKeyConstraint('doc_id', 'table_idx'),
        ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE')
    )


class DocumentCitation(Base):
    """Document citations table - outbound citations (what a paper cites)."""
    __tablename__ = "document_citations"

    citation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False)  # Document that cites
    cited_doi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_pmid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_pmcid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_nct_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_journal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_volume: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_issue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_pages: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_article_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cited_pub_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    citation_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # How it's cited
    citation_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # reference, background, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="citations")

    __table_args__ = (
        Index("idx_document_citations_doc_id", "doc_id"),
        Index("idx_document_citations_cited_doi", "cited_doi"),
        Index("idx_document_citations_cited_pmid", "cited_pmid"),
        Index("idx_document_citations_cited_pmcid", "cited_pmcid"),
        ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
    )


class DocumentEntity(Base):
    """Document entities table - LangExtract entity extraction results."""
    __tablename__ = "document_entities"

    doc_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ent_type: Mapped[str] = mapped_column(Text, nullable=False)
    value_text: Mapped[str] = mapped_column(Text, nullable=False)
    value_norm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    detector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="entities")

    __table_args__ = (
        PrimaryKeyConstraint('doc_id', 'ent_type', 'value_text', 'char_start'),
        ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        CheckConstraint("ent_type::text = ANY (ARRAY['asset_code','inn','generic','company','ticker','nct','endpoint','indication','moa','target','code']::text[])", name='ck_document_entities_ent_type'),
    )


class DocumentLink(Base):
    """Document links table - linking between docs and normalized entities."""
    __tablename__ = "document_links"

    doc_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nct_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trial_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    asset_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    company_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    link_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    heuristics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Relationships
    document: Mapped["Document"] = relationship()  # Removed back_populates since Document no longer has links relationship
    trial: Mapped[Optional["Trial"]] = relationship()
    asset: Mapped[Optional["Asset"]] = relationship()
    company: Mapped[Optional["Company"]] = relationship()

    __table_args__ = (
        PrimaryKeyConstraint('doc_id', 'nct_id', 'trial_id', 'asset_id', 'company_id'),
        ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='CASCADE'),
        ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name='ck_document_links_confidence_range'),
    )




# ---------------------------------------------------------------------------
# Span Models (Simplified)
# ---------------------------------------------------------------------------

class Span(Base):
    """Simplified spans table - text spans with location information."""
    __tablename__ = "spans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.doc_id"), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(String, nullable=False)
    page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    table_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    table_row: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    table_col: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    snippet_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bbox_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="spans")

    __table_args__ = (
        Index("ix_spans_doc_id", "doc_id"),
        Index("ix_spans_section", "section"),
        Index("ix_spans_char_range", "char_start", "char_end"),
    )



# ---------------------------------------------------------------------------
# PubMed Literature System Models
# ---------------------------------------------------------------------------

class TrialDocCandidate(Base):
    """Trial-document relationships by processing stage."""
    __tablename__ = "trial_doc_candidates"

    trial_id: Mapped[int] = mapped_column(Integer, nullable=False)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    selected: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dropped_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    trial: Mapped["Trial"] = relationship(back_populates=None)
    document: Mapped["Document"] = relationship()  # Removed back_populates since Document no longer has trial_candidates relationship

    __table_args__ = (
        PrimaryKeyConstraint('trial_id', 'doc_id'),
        ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        CheckConstraint("stage::text = ANY (ARRAY['U0_meta','U1_discovery','U1_abstract','OA_fulltext']::text[])", name='ck_trial_doc_candidates_stage')
    )


class PubMedMeta(Base):
    """PubMed-specific metadata for documents."""
    __tablename__ = "pubmed_meta"

    doc_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pmid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    medline_xml_sha: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    affiliations: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    esummary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    efetch_header: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="pubmed_meta")

    __table_args__ = (
        ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
    )


class PmcMeta(Base):
    """PMC-specific metadata for documents."""
    __tablename__ = "pmc_meta"

    doc_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pmcid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    license: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    oa_route: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    oai_identifier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="pmc_meta")

    __table_args__ = (
        ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
    )


class TrialLitState(Base):
    """Trial-level literature state and metrics."""
    __tablename__ = "trial_lit_state"

    trial_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    best_S_Rge2: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    n_docs_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    n_docs_selected: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    p_short: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    uncertainty: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    max_expected_utility_next_doc: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default='active')

    # Relationships
    trial: Mapped["Trial"] = relationship(back_populates=None)

    __table_args__ = (
        ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        CheckConstraint("best_S_Rge2 IS NULL OR (best_S_Rge2 >= 0 AND best_S_Rge2 <= 1)", name='ck_trial_lit_state_best_S_Rge2_range'),
        CheckConstraint("p_short IS NULL OR (p_short >= 0 AND p_short <= 1)", name='ck_trial_lit_state_p_short_range'),
        CheckConstraint("uncertainty IS NULL OR (uncertainty >= 0 AND uncertainty <= 1)", name='ck_trial_lit_state_uncertainty_range'),
        CheckConstraint("max_expected_utility_next_doc IS NULL OR (max_expected_utility_next_doc >= 0 AND max_expected_utility_next_doc <= 1)", name='ck_trial_lit_state_utility_range'),
        CheckConstraint("status::text = ANY (ARRAY['active','stopped','parked','promoted']::text[])", name='ck_trial_lit_state_status')
    )


class CtgovIngestState(Base):
    """CT.gov ingestion state tracking."""
    __tablename__ = "ctgov_ingest_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    last_ingest_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingest_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ingest_status: Mapped[str] = mapped_column(Text, nullable=False, server_default='idle')
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("ingest_status::text = ANY (ARRAY['idle','running','completed','failed']::text[])", name='ck_ctgov_ingest_state_status'),
    )


class Task(Base):
    """Processing queue for pipeline tasks."""
    __tablename__ = "processing_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    task_key: Mapped[str] = mapped_column(Text, nullable=False)
    trial_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    company_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    priority: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default='queued')
    leased_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    leased_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB(astext_type=Text), nullable=False, server_default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("task_type", "task_key", name="uq_processing_queue_type_key"),
        CheckConstraint(
            "status IN ('queued','leased','done','failed','parked','canceled')",
            name="ck_processing_queue_status_valid",
        ),
    )


# ---------------------------------------------------------------------------
# Entity Pack System Models - REMOVED
# ---------------------------------------------------------------------------
# Entity packs are now handled in-memory via src/ncfd/entities/schema.py
# No database tables needed for the simplified entity system


# ---------------------------------------------------------------------------
# Simplified Resolver System Models
# ---------------------------------------------------------------------------

class SponsorResolution(Base):
    """Simplified sponsor resolution results."""
    __tablename__ = "sponsor_resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nct_id: Mapped[str] = mapped_column(String(20), nullable=False)
    sponsor_text: Mapped[str] = mapped_column(Text, nullable=False)
    sponsor_text_norm: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companies.company_id"), nullable=True)
    match_method: Mapped[str] = mapped_column(String(20), nullable=False)  # exact, fuzzy, llm, manual
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB(astext_type=Text), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    company: Mapped[Optional["Company"]] = relationship("Company", foreign_keys=[company_id])

    __table_args__ = (
        UniqueConstraint("nct_id", "sponsor_text_norm", name="uq_sponsor_resolutions_nct_sponsor"),
        Index("idx_sponsor_resolutions_nct_id", "nct_id"),
        Index("idx_sponsor_resolutions_company_id", "company_id"),
        Index("idx_sponsor_resolutions_match_method", "match_method"),
        CheckConstraint(
            "match_method IN ('exact', 'fuzzy', 'llm', 'manual')",
            name="ck_sponsor_resolutions_match_method_valid",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_sponsor_resolutions_confidence_valid",
        ),
    )


class ManualReviewQueue(Base):
    """Simplified manual review queue."""
    __tablename__ = "manual_review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nct_id: Mapped[str] = mapped_column(String(20), nullable=False)
    sponsor_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default='pending')
    assigned_company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companies.company_id"), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    assigned_company: Mapped[Optional["Company"]] = relationship("Company", foreign_keys=[assigned_company_id])

    __table_args__ = (
        Index("idx_manual_review_queue_status", "status"),
        Index("idx_manual_review_queue_nct_id", "nct_id"),
        CheckConstraint(
            "status IN ('pending', 'completed', 'skipped')",
            name="ck_manual_review_queue_status_valid",
        ),
    )


class AcademicBlacklist(Base):
    """Precise academic institution patterns."""
    __tablename__ = "academic_blacklist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default='true')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LLMDiscovery(Base):
    """Track LLM learning and discoveries."""
    __tablename__ = "llm_discoveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nct_id: Mapped[str] = mapped_column(String(20), nullable=False)
    sponsor_text: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companies.company_id"), nullable=True)
    discovered_aliases: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB(astext_type=Text), nullable=True)
    llm_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB(astext_type=Text), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    discovered_company: Mapped[Optional["Company"]] = relationship("Company", foreign_keys=[discovered_company_id])

    __table_args__ = (
        Index("idx_llm_discoveries_nct_id", "nct_id"),
        Index("idx_llm_discoveries_company_id", "discovered_company_id"),
    )


# ---------------------------------------------------------------------------
# Study Card Models (consolidated from study_card_models.py)
# ---------------------------------------------------------------------------

class StudyCard(Base):
    """SQLAlchemy model for study_cards table."""
    __tablename__ = 'study_cards'
    
    study_card_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.doc_id"), nullable=False)
    design_archetype: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_blinded: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    analysis_set: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    population_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stratification_factors: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    covariate_adjustment: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    primary_endpoint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    secondary_endpoints: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    summary_measure: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    alpha_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_one_sided: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    multiplicity_adjustment: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sample_size_reassessment: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    interim_looks: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    interim_timing: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    spending_function: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stop_rules: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    missingness_assumption: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    missingness_pattern: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    imputation_method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    estimand: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intercurrent_events_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    endpoint_ascertainment: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    assessment_interval: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    adjudication_committee: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # New versioning columns
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    authored_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    p_fail: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gates_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    summary_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risks_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    methods_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    document: Mapped[Optional["Document"]] = relationship("Document", foreign_keys=[doc_id], primaryjoin="StudyCard.doc_id == Document.doc_id")

    __table_args__ = (
        Index("idx_study_cards_doc_id", "doc_id"),
        Index("idx_study_cards_version", "version"),
        Index("idx_study_cards_created_at", "created_at"),
        Index("idx_study_cards_design_archetype", "design_archetype"),
        Index("idx_study_cards_model_name", "model_name"),
    )


class Factsheet(Base):
    """SQLAlchemy model for factsheets table."""
    __tablename__ = 'factsheets'
    
    factsheet_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.doc_id"), nullable=False)
    results: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    primary_endpoint_results: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    secondary_endpoint_results: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    safety_results: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    primary_analysis_set: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    secondary_analysis_sets: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    total_enrolled: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completed_primary_endpoint: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dropout_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    follow_up_completion: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    document: Mapped[Optional["Document"]] = relationship("Document", foreign_keys=[doc_id], primaryjoin="Factsheet.doc_id == Document.doc_id")

    __table_args__ = (
        Index("idx_factsheets_doc_id", "doc_id"),
        Index("idx_factsheets_created_at", "created_at"),
        Index("idx_factsheets_total_enrolled", "total_enrolled"),
        Index("idx_factsheets_dropout_rate", "dropout_rate"),
    )


class PatternFamily(Base):
    """SQLAlchemy model for pattern_families table."""
    __tablename__ = 'pattern_families'
    
    family_id: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    # Relationships
    pattern_detections: Mapped[List["PatternDetection"]] = relationship("PatternDetection", foreign_keys="PatternDetection.family_id", primaryjoin="PatternFamily.family_id == PatternDetection.family_id")


class PatternDetection(Base):
    """SQLAlchemy model for pattern_detections table."""
    __tablename__ = 'pattern_detections'
    
    detection_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trial_id: Mapped[int] = mapped_column(Integer, ForeignKey("trials.trial_id"), nullable=False)
    run_id: Mapped[str] = mapped_column(String(50), nullable=False)
    family_id: Mapped[str] = mapped_column(String(2), ForeignKey("pattern_families.family_id"), nullable=False)
    pattern_id: Mapped[str] = mapped_column(String(4), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_spans: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    detected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    # Relationships
    trial: Mapped[Optional["Trial"]] = relationship("Trial", foreign_keys=[trial_id], primaryjoin="PatternDetection.trial_id == Trial.trial_id")
    pattern_family: Mapped[Optional["PatternFamily"]] = relationship("PatternFamily", foreign_keys=[family_id], primaryjoin="PatternDetection.family_id == PatternFamily.family_id")

    __table_args__ = (
        Index("idx_pattern_detections_trial", "trial_id"),
        Index("idx_pattern_detections_family", "family_id"),
        Index("idx_pattern_detections_run", "run_id"),
        Index("idx_pattern_detections_severity", "severity"),
    )
