# src/ncfd/db/models.py
from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String, Text, Boolean, Date, DateTime, ForeignKey, Index,
    UniqueConstraint, Integer, BigInteger, CheckConstraint, event, func,
    PrimaryKeyConstraint, Numeric
)

from sqlalchemy.dialects.postgresql import ARRAY, JSONB, DATERANGE, ENUM as PGEnum

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """SQLAlchemy declarative base for ncfd models."""
    pass

# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

from ncfd.mapping.normalize import norm_name, norm_ticker  # ensure this module exists

# ---------------------------------------------------------------------------
# Issuer / Exchange domain
# ---------------------------------------------------------------------------

class Exchange(Base):
    __tablename__ = "exchanges"

    exchange_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code:        Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    mic:         Mapped[Optional[str]] = mapped_column(Text, unique=True)
    name:        Mapped[str] = mapped_column(Text, nullable=False)
    country:     Mapped[str] = mapped_column(Text, nullable=False, default="US")
    is_allowed:  Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # NOTE: attribute named metadata_ to avoid SQLAlchemy reserved name 'metadata'
    metadata_:   Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)

    securities: Mapped[List["Security"]] = relationship(back_populates="exchange")


class Company(Base):
    __tablename__ = "companies"

    company_id:      Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik:             Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name:            Mapped[str] = mapped_column(Text, nullable=False)
    name_norm:       Mapped[str] = mapped_column(Text, nullable=False)
    state_incorp:    Mapped[Optional[str]] = mapped_column(Text)
    country_incorp:  Mapped[Optional[str]] = mapped_column(Text)
    sic:             Mapped[Optional[str]] = mapped_column(Text)
    website_domain:  Mapped[Optional[str]] = mapped_column(Text)
    lei:             Mapped[Optional[str]] = mapped_column(Text)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    metadata_:       Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)

    aliases: Mapped[List["CompanyAlias"]] = relationship(
            back_populates="company",
            cascade="all, delete-orphan",
            foreign_keys="CompanyAlias.company_id",
            primaryjoin="Company.company_id == CompanyAlias.company_id",
        )

    securities: Mapped[List["Security"]] = relationship(
            back_populates="company",
            cascade="all, delete-orphan",
        )

    __table_args__ = (
        CheckConstraint("cik >= 1 AND cik <= 9999999999", name="ck_companies_cik_range"),
        Index("idx_companies_name_norm", "name_norm"),
        UniqueConstraint("cik", name="uq_companies_cik"),
    )


@event.listens_for(Company, "before_insert")
def _company_bi(_, __, target: Company):
    target.name_norm = norm_name(target.name)


@event.listens_for(Company, "before_update")
def _company_bu(_, __, target: Company):
    if target.name:
        target.name_norm = norm_name(target.name)


class CompanyAlias(Base):
    __tablename__ = "company_aliases"
    __table_args__ = (
        UniqueConstraint("company_id", "alias_norm", "alias_type", name="uq_alias_by_company_norm_type"),
        CheckConstraint("(confidence IS NULL) OR (confidence >= 0 AND confidence <= 1)", name="ck_alias_confidence"),
        Index("idx_alias_norm", "alias_norm"),
    )

    alias_id:         Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id:       Mapped[int] = mapped_column(ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False)
    alias:            Mapped[str] = mapped_column(Text, nullable=False)
    alias_norm:       Mapped[str] = mapped_column(Text, nullable=False)
    alias_type:       Mapped[str] = mapped_column(
        PGEnum(
            "aka", "dba", "former_name", "short", "subsidiary", "brand", "domain", "other",
            name="alias_type", create_type=False
        ),
        nullable=False,
    )
    source:           Mapped[Optional[str]] = mapped_column(Text)
    source_url:       Mapped[Optional[str]] = mapped_column(Text)
    start_date:       Mapped[Optional[date]] = mapped_column(Date)
    end_date:         Mapped[Optional[date]] = mapped_column(Date)
    confidence:       Mapped[Optional[float]]
    alias_company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.company_id"))
    created_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_:        Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)

    company: Mapped["Company"] = relationship(
            back_populates="aliases",
            foreign_keys="[CompanyAlias.company_id]",
            primaryjoin="Company.company_id == CompanyAlias.company_id",
        )
    alias_company: Mapped[Optional["Company"]] = relationship(
            foreign_keys="[CompanyAlias.alias_company_id]",
            primaryjoin="Company.company_id == CompanyAlias.alias_company_id",
            viewonly=True,   # keep it simple; we don't write through this rel
        )

@event.listens_for(CompanyAlias, "before_insert")
def _alias_bi(_, __, target: CompanyAlias):
    target.alias_norm = norm_name(target.alias)


@event.listens_for(CompanyAlias, "before_update")
def _alias_bu(_, __, target: CompanyAlias):
    if target.alias:
        target.alias_norm = norm_name(target.alias)


class Security(Base):
    __tablename__ = "securities"

    security_id:        Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id:         Mapped[int] = mapped_column(ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False)
    exchange_id:        Mapped[int] = mapped_column(ForeignKey("exchanges.exchange_id"), nullable=False)
    ticker:             Mapped[str] = mapped_column(Text, nullable=False)
    ticker_norm:        Mapped[str] = mapped_column(Text, nullable=False)
    type:               Mapped[str] = mapped_column(
        PGEnum(
            "common", "adr", "preferred", "warrant", "unit", "right", "etf", "other",
            name="security_type", create_type=False
        ),
        nullable=False,
        default="common",
    )
    status:             Mapped[str] = mapped_column(
        PGEnum(
            "active", "delisted", "suspended", "pending", "acquired",
            name="security_status", create_type=False
        ),
        nullable=False,
        default="active",
    )
    is_primary_listing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_range:    Mapped[object] = mapped_column(DATERANGE, nullable=False)
    currency:           Mapped[str] = mapped_column(Text, nullable=False, default="USD")
    figi:               Mapped[Optional[str]] = mapped_column(Text)
    cik:                Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    metadata_:          Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)

    company:  Mapped["Company"]  = relationship(back_populates="securities")
    exchange: Mapped["Exchange"] = relationship(back_populates="securities")

@event.listens_for(Security, "before_insert")
def _sec_bi(_, __, target: Security):
    target.ticker_norm = norm_ticker(target.ticker)


@event.listens_for(Security, "before_update")
def _sec_bu(_, __, target: Security):
    if target.ticker:
        target.ticker_norm = norm_ticker(target.ticker)

# ---------------------------------------------------------------------------
# Core clinical-trial entities (unchanged)
# ---------------------------------------------------------------------------

class Trial(Base):
    __tablename__ = "trials"

    trial_id: Mapped[int] = mapped_column(primary_key=True)
    nct_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    sponsor_text: Mapped[Optional[str]] = mapped_column(String, default=None)
    sponsor_company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.company_id"),
        default=None,
    )
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

    versions: Mapped[List["TrialVersion"]] = relationship(
        back_populates="trial",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_trials_status", "status"),
        Index("idx_trials_is_pivotal", "is_pivotal"),
        Index("idx_trials_last_update", "last_update_posted_date"),
    )


class TrialVersion(Base):
    __tablename__ = "trial_versions"

    trial_version_id: Mapped[int] = mapped_column(primary_key=True)
    trial_id: Mapped[int] = mapped_column(
        ForeignKey("trials.trial_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    last_update_posted_date: Mapped[Optional[date]] = mapped_column(Date, default=None)

    from sqlalchemy import Integer as _Int  # local alias to avoid shadowing
    raw_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    primary_endpoint_text: Mapped[Optional[str]] = mapped_column(String, default=None)
    sample_size: Mapped[Optional[int]] = mapped_column(_Int, default=None)
    analysis_plan_text: Mapped[Optional[str]] = mapped_column(String, default=None)
    changes_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB, default=None)

    changed_primary_endpoint: Mapped[Optional[bool]] = mapped_column(Boolean, default=None)
    changed_sample_size: Mapped[Optional[bool]] = mapped_column(Boolean, default=None)
    sample_size_delta: Mapped[Optional[int]] = mapped_column(_Int, default=None)
    changed_analysis_plan: Mapped[Optional[bool]] = mapped_column(Boolean, default=None)

    trial: Mapped["Trial"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("trial_id", "sha256", name="uq_trial_version_hash"),
        Index("idx_trial_versions_trial_time", "trial_id", "captured_at"),
        Index(
            "idx_trial_versions_changed",
            "changed_primary_endpoint",
            "changed_sample_size",
            "changed_analysis_plan",
        ),
        Index("idx_trial_versions_updated", "last_update_posted_date"),
    )


class CtgovHistoryVersion(Base):
    __tablename__ = "ctgov_history_versions"

    trial_id: Mapped[int] = mapped_column(
        ForeignKey("trials.trial_id", ondelete="CASCADE"),
        primary_key=True,
    )
    version_rank: Mapped[int] = mapped_column(primary_key=True)
    submitted_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    url: Mapped[Optional[str]] = mapped_column(String, default=None)


class Study(Base):
    __tablename__ = "studies"

    study_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)  # PR, Abstract, Paper, Registry, FDA
    citation: Mapped[Optional[str]] = mapped_column(Text)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text)
    oa_status: Mapped[str] = mapped_column(Text, server_default="unknown")  # open, green, bronze, closed, unknown
    extracted_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB)  # Study Card JSON
    coverage_level: Mapped[Optional[str]] = mapped_column(Text)  # high, med, low
    notes_md: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    trial: Mapped["Trial"] = relationship()
    document_links: Mapped[List["DocumentLink"]] = relationship(back_populates="study")

    __table_args__ = (
        Index("ix_studies_trial", "trial_id"),
        Index("ix_studies_coverage", "coverage_level"),
        Index("ix_studies_year", "year"),
        Index("ix_studies_doc_type", "doc_type"),
    )


class CtgovIngestState(Base):
    __tablename__ = "ctgov_ingest_state"

    id: Mapped[bool] = mapped_column(primary_key=True, default=True)
    cursor_last_update_posted: Mapped[Optional[date]] = mapped_column(Date, default=None)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    run_id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    since_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    until_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    total_returned: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    total_processed: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    notes: Mapped[Optional[str]] = mapped_column(String, default=None)


# ---------------------------------------------------------------------------
# Asset domain
# ---------------------------------------------------------------------------

class Asset(Base):
    __tablename__ = "assets"

    asset_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    names_jsonb: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    modality: Mapped[Optional[str]] = mapped_column(Text)
    target: Mapped[Optional[str]] = mapped_column(Text)
    moa: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    aliases: Mapped[List["AssetAlias"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
    )

    document_links: Mapped[List["DocumentLink"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
    )


class AssetAlias(Base):
    __tablename__ = "asset_aliases"

    asset_alias_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    alias_norm: Mapped[str] = mapped_column(Text, nullable=False)
    alias_type: Mapped[str] = mapped_column(Text, nullable=False)  # inn, generic, brand, code, chembl, drugbank, unii, cas, inchikey, other
    source: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset: Mapped["Asset"] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("asset_id", "alias_norm", "alias_type", name="uq_asset_alias_norm_type"),
        Index("ix_asset_alias_norm", "alias_norm"),
    )


# ---------------------------------------------------------------------------
# Document staging domain
# ---------------------------------------------------------------------------

class Document(Base):
    __tablename__ = "documents"

    doc_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)  # PR, IR, Abstract, Paper, Registry, FDA, SEC_8K, Other
    source_url: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    publisher: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    oa_status: Mapped[str] = mapped_column(Text, server_default="unknown")  # open, green, bronze, closed, unknown
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    parsed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default="discovered", nullable=False)  # discovered, fetched, parsed, indexed, linked, ready_for_card, card_built, error
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    crawl_run_id: Mapped[Optional[str]] = mapped_column(Text)

    text_pages: Mapped[List["DocumentTextPage"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    tables: Mapped[List["DocumentTable"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    links: Mapped[List["DocumentLink"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    entities: Mapped[List["DocumentEntity"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    citations: Mapped[Optional["DocumentCitation"]] = relationship(
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )

    notes: Mapped[Optional["DocumentNote"]] = relationship(
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_documents_sha256", "sha256"),
        Index("ix_documents_published_at", "published_at"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_type_date", "source_type", "published_at", postgresql_ops={"published_at": "DESC"}),
    )


class DocumentTextPage(Base):
    __tablename__ = "document_text_pages"

    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False)
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="text_pages")

    __table_args__ = (
        PrimaryKeyConstraint("doc_id", "page_no"),
    )


class DocumentTable(Base):
    __tablename__ = "document_tables"

    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False)
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    table_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    table_jsonb: Mapped[dict] = mapped_column(JSONB, nullable=False)
    detector: Mapped[Optional[str]] = mapped_column(Text)

    document: Mapped["Document"] = relationship(back_populates="tables")

    __table_args__ = (
        PrimaryKeyConstraint("doc_id", "page_no", "table_idx"),
    )


class DocumentLink(Base):
    __tablename__ = "document_links"

    link_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False)
    study_id: Mapped[Optional[int]] = mapped_column(ForeignKey("studies.study_id", ondelete="SET NULL"))
    nct_id: Mapped[Optional[str]] = mapped_column(Text)
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.asset_id", ondelete="SET NULL"))
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.company_id", ondelete="SET NULL"))
    link_type: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="links")
    study: Mapped[Optional["Study"]] = relationship(back_populates="document_links")
    asset: Mapped[Optional["Asset"]] = relationship(back_populates="document_links")
    company: Mapped[Optional["Company"]] = relationship()

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_doclinks_confidence"),
        Index("ix_doclinks_doc", "doc_id"),
        Index("ix_doclinks_asset", "asset_id"),
        Index("ix_doclinks_nct", "nct_id"),
    )


class DocumentEntity(Base):
    __tablename__ = "document_entities"

    entity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False)
    ent_type: Mapped[str] = mapped_column(Text, nullable=False)  # endpoint, n_total, p_value, effect_size, population, subgroup, code, inn, generic
    value_text: Mapped[str] = mapped_column(Text, nullable=False)
    value_norm: Mapped[Optional[str]] = mapped_column(Text)
    page_no: Mapped[Optional[int]] = mapped_column(Integer)
    char_start: Mapped[Optional[int]] = mapped_column(Integer)
    char_end: Mapped[Optional[int]] = mapped_column(Integer)
    detector: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="entities")

    __table_args__ = (
        Index("ix_docents_doc", "doc_id"),
        Index("ix_docents_type", "ent_type"),
        Index("ix_document_entities_confidence", "confidence"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_document_entities_confidence"),
    )


class DocumentCitation(Base):
    __tablename__ = "document_citations"

    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), primary_key=True)
    doi: Mapped[Optional[str]] = mapped_column(Text)
    pmid: Mapped[Optional[str]] = mapped_column(Text)
    pmcid: Mapped[Optional[str]] = mapped_column(Text)
    crossref_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB)
    unpaywall_jsonb: Mapped[Optional[dict]] = mapped_column(JSONB)

    document: Mapped["Document"] = relationship(back_populates="citations")


class DocumentNote(Base):
    __tablename__ = "document_notes"

    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), primary_key=True)
    notes_md: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    document: Mapped["Document"] = relationship(back_populates="notes")


# ---------------------------------------------------------------------------
# Final xref tables (promoted links)
# ---------------------------------------------------------------------------

class StudyAssetsXref(Base):
    __tablename__ = "study_assets_xref"

    xref_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    study_id: Mapped[str] = mapped_column(Text, nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    evidence_jsonb: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    link_source: Mapped[str] = mapped_column(Text, nullable=False)
    how: Mapped[str] = mapped_column(Text, nullable=False)  # How the link was established
    source_doc_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.doc_id", ondelete="SET NULL"))
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    promoted_by: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="active", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    asset: Mapped["Asset"] = relationship()
    source_document: Mapped[Optional["Document"]] = relationship()

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_study_assets_confidence"),
        UniqueConstraint("study_id", "asset_id", name="uq_study_assets_study_asset"),
        Index("ix_study_assets_xref_study", "study_id"),
        Index("ix_study_assets_xref_asset", "asset_id"),
        Index("ix_study_assets_xref_confidence", "confidence"),
        Index("ix_study_assets_xref_status", "status"),
    )


class TrialAssetsXref(Base):
    __tablename__ = "trial_assets_xref"

    xref_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    evidence_jsonb: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    link_source: Mapped[str] = mapped_column(Text, nullable=False)
    how: Mapped[str] = mapped_column(Text, nullable=False)  # How the link was established
    source_doc_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.doc_id", ondelete="SET NULL"))
    promoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    promoted_by: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="active", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    asset: Mapped["Asset"] = relationship()
    source_document: Mapped[Optional["Document"]] = relationship()
    trial: Mapped["Trial"] = relationship()

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_trial_assets_confidence"),
        UniqueConstraint("trial_id", "asset_id", name="uq_trial_assets_trial_asset"),
        Index("ix_trial_assets_xref_trial", "trial_id"),
        Index("ix_trial_assets_xref_asset", "asset_id"),
        Index("ix_trial_assets_xref_confidence", "confidence"),
        Index("ix_trial_assets_xref_status", "status"),
    )


class LinkAudit(Base):
    __tablename__ = "link_audit"

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    nct_id: Mapped[Optional[str]] = mapped_column(Text)
    link_type: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    heuristic_applied: Mapped[Optional[str]] = mapped_column(Text)
    evidence_jsonb: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    promotion_status: Mapped[str] = mapped_column(Text, server_default="pending", nullable=False)
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    document: Mapped["Document"] = relationship()
    asset: Mapped["Asset"] = relationship()

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_link_audit_confidence"),
        Index("ix_link_audit_doc", "doc_id"),
        Index("ix_link_audit_asset", "asset_id"),
        Index("ix_link_audit_nct", "nct_id"),
        Index("ix_link_audit_confidence", "confidence"),
        Index("ix_link_audit_promotion_status", "promotion_status"),
        Index("ix_link_audit_heuristic", "heuristic_applied"),
    )


class MergeCandidate(Base):
    __tablename__ = "merge_candidates"

    merge_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id_1: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    asset_id_2: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False)
    merge_reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_jsonb: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="pending", nullable=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    asset_1: Mapped["Asset"] = relationship(foreign_keys=[asset_id_1])
    asset_2: Mapped["Asset"] = relationship(foreign_keys=[asset_id_2])

    __table_args__ = (
        CheckConstraint("asset_id_1 != asset_id_2", name="ck_merge_candidates_different"),
        Index("ix_merge_candidates_asset1", "asset_id_1"),
        Index("ix_merge_candidates_asset2", "asset_id_2"),
        Index("ix_merge_candidates_status", "status"),
    )
