# src/ncfd/db/models.py
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, Date, DateTime, BigInteger, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB


class Base(DeclarativeBase):
    pass

class Company(Base):
    __tablename__ = "companies"
    company_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String, default=None)

class Trial(Base):
    __tablename__ = "trials"

    trial_id: Mapped[int] = mapped_column(primary_key=True)
    nct_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    sponsor_text: Mapped[Optional[str]] = mapped_column(String, default=None)
    sponsor_company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.company_id"), default=None)
    phase: Mapped[Optional[str]] = mapped_column(String, default=None)
    indication: Mapped[Optional[str]] = mapped_column(String, default=None)
    is_pivotal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    primary_endpoint_text: Mapped[Optional[str]] = mapped_column(String, default=None)
    est_primary_completion_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    status: Mapped[Optional[str]] = mapped_column(String, default=None)
    first_posted_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    last_update_posted_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    intervention_types: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), default=None)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    current_sha256: Mapped[Optional[str]] = mapped_column(String(64), default=None)

    versions: Mapped[List["TrialVersion"]] = relationship(back_populates="trial", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_trials_status", "status"),
        Index("idx_trials_is_pivotal", "is_pivotal"),
        Index("idx_trials_last_update", "last_update_posted_date"),
    )


class TrialVersion(Base):
    __tablename__ = "trial_versions"

    trial_version_id: Mapped[int] = mapped_column(primary_key=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    last_update_posted_date: Mapped[Optional[date]] = mapped_column(Date, default=None)

    raw_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    primary_endpoint_text: Mapped[Optional[str]] = mapped_column(String, default=None)
    sample_size: Mapped[Optional[int]] = mapped_column(default=None)
    analysis_plan_text: Mapped[Optional[str]] = mapped_column(String, default=None)
    changes_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB, default=None)

    changed_primary_endpoint: Mapped[Optional[bool]] = mapped_column(Boolean, default=None)
    changed_sample_size: Mapped[Optional[bool]] = mapped_column(Boolean, default=None)
    sample_size_delta: Mapped[Optional[int]] = mapped_column(default=None)
    changed_analysis_plan: Mapped[Optional[bool]] = mapped_column(Boolean, default=None)

    trial: Mapped[Trial] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("trial_id", "sha256", name="uq_trial_version_hash"),
        Index("idx_trial_versions_trial_time", "trial_id", "captured_at"),
        Index("idx_trial_versions_changed", "changed_primary_endpoint", "changed_sample_size", "changed_analysis_plan"),
        Index("idx_trial_versions_updated", "last_update_posted_date"),
    )


class CtgovHistoryVersion(Base):
    __tablename__ = "ctgov_history_versions"

    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True)
    version_rank: Mapped[int] = mapped_column(primary_key=True)
    submitted_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    url: Mapped[Optional[str]] = mapped_column(String, default=None)


class CtgovIngestState(Base):
    __tablename__ = "ctgov_ingest_state"

    id: Mapped[bool] = mapped_column(primary_key=True, default=True)
    cursor_last_update_posted: Mapped[Optional[date]] = mapped_column(Date, default=None)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    run_id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    since_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    until_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    total_returned: Mapped[Optional[int]] = mapped_column(default=None)
    total_processed: Mapped[Optional[int]] = mapped_column(default=None)
    notes: Mapped[Optional[str]] = mapped_column(String, default=None)
