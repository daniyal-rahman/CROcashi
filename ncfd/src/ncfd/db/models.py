"""Database models for core trial data."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base


Base = declarative_base()


# --- Reference tables -------------------------------------------------------


class Company(Base):
    """Public company issuing a security."""

    __tablename__ = "companies"

    company_id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    ticker = Column(String(10))
    cik = Column(String(10))


class Asset(Base):
    """Therapeutic asset tracked across trials."""

    __tablename__ = "assets"

    asset_id = Column(Integer, primary_key=True)
    names_jsonb = Column(JSONB)
    modality = Column(Text)
    target = Column(Text)
    moa = Column(Text)


class Trial(Base):
    """Normalized clinical trial record."""

    __tablename__ = "trials"

    trial_id = Column(Integer, primary_key=True)
    nct_id = Column(Text, nullable=False, unique=True)
    sponsor_text = Column(Text)
    sponsor_company_id = Column(Integer, ForeignKey("companies.company_id"))
    phase = Column(Text)
    indication = Column(Text)
    is_pivotal = Column(Boolean, nullable=False, default=False)
    primary_endpoint_text = Column(Text)
    est_primary_completion_date = Column(Date)
    status = Column(Text)
    first_posted_date = Column(Date)
    last_update_posted_date = Column(Date)
    intervention_types = Column(ARRAY(Text))
    last_seen_at = Column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    current_sha256 = Column(String(64))

    __table_args__ = (
        CheckConstraint("nct_id ~ '^NCT[0-9]{8}$'", name="chk_nct"),
    )


class TrialVersion(Base):
    """Forward-captured snapshot of a trial record."""

    __tablename__ = "trial_versions"

    trial_version_id = Column(Integer, primary_key=True)
    trial_id = Column(Integer, ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    last_update_posted_date = Column(Date)
    raw_jsonb = Column(JSONB, nullable=False)
    sha256 = Column(String(64), nullable=False)
    primary_endpoint_text = Column(Text)
    sample_size = Column(Integer)
    analysis_plan_text = Column(Text)
    changes_jsonb = Column(JSONB)

    __table_args__ = (
        UniqueConstraint("trial_id", "sha256", name="uq_trial_versions_trial_sha"),
        Index("idx_trial_versions_trial_time", "trial_id", "captured_at"),
        Index("idx_trial_versions_hash", "sha256"),
    )


class CTGovHistoryVersion(Base):
    """Metadata scraped from the ClinicalTrials.gov Record History page."""

    __tablename__ = "ctgov_history_versions"

    trial_id = Column(Integer, ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True)
    version_rank = Column(Integer, primary_key=True)
    submitted_date = Column(Date)
    url = Column(Text)


class CTGovIngestState(Base):
    """Singleton table tracking cursor position for CT.gov ingestion."""

    __tablename__ = "ctgov_ingest_state"

    id = Column(Boolean, primary_key=True, default=True)
    cursor_last_update_posted = Column(Date)
    last_run_at = Column(DateTime(timezone=True))


class IngestRun(Base):
    """Audit log for ingestion runs."""

    __tablename__ = "ingest_runs"

    run_id = Column(Integer, primary_key=True)
    source = Column(Text, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime(timezone=True))
    since_date = Column(Date)
    until_date = Column(Date)
    total_returned = Column(Integer)
    total_processed = Column(Integer)
    notes = Column(Text)


class Study(Base):
    """External document providing evidence about a trial."""

    __tablename__ = "studies"

    study_id = Column(Integer, primary_key=True)
    trial_id = Column(Integer, ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.asset_id"))
    doc_type = Column(Text)  # e.g. PR, Abstract, Paper
    citation = Column(Text)
    year = Column(Integer)
    url = Column(Text)
    oa_status = Column(Text)
    extracted_jsonb = Column(JSONB)
    notes_md = Column(Text)
    coverage_level = Column(Integer)


class Signal(Base):
    """Primitive signal extracted from a study."""

    __tablename__ = "signals"

    trial_id = Column(Integer, ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True)
    s_id = Column(Text, primary_key=True)
    value = Column(Float)
    severity = Column(Text)
    evidence_span = Column(Text)
    source_study_id = Column(Integer, ForeignKey("studies.study_id"))


class Gate(Base):
    """Composite gate built from multiple signals."""

    __tablename__ = "gates"

    trial_id = Column(Integer, ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True)
    g_id = Column(Text, primary_key=True)
    fired_bool = Column(Boolean, nullable=False)
    supporting_s_ids = Column(ARRAY(Text))
    lr_used = Column(Float)
    rationale_text = Column(Text)


class Score(Base):
    """Posterior failure probability for a trial."""

    __tablename__ = "scores"

    trial_id = Column(Integer, ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True)
    run_id = Column(Integer, primary_key=True)
    prior_pi = Column(Float)
    logit_prior = Column(Float)
    sum_log_lr = Column(Float)
    logit_post = Column(Float)
    p_fail = Column(Float)


class AssetOwnership(Base):
    """Ownership periods of an asset by a company."""

    __tablename__ = "asset_ownership"

    asset_id = Column(Integer, ForeignKey("assets.asset_id", ondelete="CASCADE"), primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.company_id", ondelete="CASCADE"), primary_key=True)
    start_date = Column(Date, primary_key=True)
    end_date = Column(Date)
    source = Column(Text)
    evidence_url = Column(Text)


class Patent(Base):
    """Patent associated with an asset."""

    __tablename__ = "patents"

    patent_id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.asset_id", ondelete="CASCADE"))
    family_id = Column(Text)
    jurisdiction = Column(Text)
    number = Column(Text)
    earliest_priority_date = Column(Date)
    assignees = Column(ARRAY(Text))
    inventors = Column(ARRAY(Text))
    status = Column(Text)


class PatentAssignment(Base):
    """Assignment record for a patent."""

    __tablename__ = "patent_assignments"

    assignment_id = Column(Integer, primary_key=True)
    patent_id = Column(Integer, ForeignKey("patents.patent_id", ondelete="CASCADE"), nullable=False)
    assignor = Column(Text)
    assignee = Column(Text)
    exec_date = Column(Date)
    type = Column(Text)
    source_url = Column(Text)


class Label(Base):
    """Outcome label for a trial readout."""

    __tablename__ = "labels"

    trial_id = Column(Integer, ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True)
    event_date = Column(Date, primary_key=True)
    primary_outcome_success_bool = Column(Boolean)
    price_move_5d = Column(Float)
    label_source_url = Column(Text)


class Catalyst(Base):
    """Important upcoming trial catalyst windows."""

    __tablename__ = "catalysts"

    trial_id = Column(Integer, ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True)
    window_start = Column(Date, primary_key=True)
    window_end = Column(Date)
    certainty = Column(Float)
    sources = Column(ARRAY(Text))


__all__ = [
    "Base",
    "Company",
    "Asset",
    "Trial",
    "TrialVersion",
    "CTGovHistoryVersion",
    "CTGovIngestState",
    "IngestRun",
    "Study",
    "Signal",
    "Gate",
    "Score",
    "AssetOwnership",
    "Patent",
    "PatentAssignment",
    "Label",
    "Catalyst",
]

