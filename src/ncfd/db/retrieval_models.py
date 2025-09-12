"""
Retrieval Models - Dual persistence strategy for PubMed pipeline.

Implements the dual persistence strategy:
1. retrieval_documents: Stores ALL documents found during retrieval (human verification)
2. processed_documents: Stores only filtered, processed documents (LLM processing)
3. retrieval_sessions: Tracks retrieval runs for audit
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import String, Text, Boolean, DateTime, Float, ForeignKey, Index, CheckConstraint, Integer, func, ForeignKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from .models import Base


class RetrievalSession(Base):
    """Tracks retrieval runs for audit and debugging purposes."""
    __tablename__ = "retrieval_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_aliases: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    indication_terms: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    query_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    total_documents_found: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    documents_after_policy_engine: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    documents_after_guardrails: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    documents_after_processing: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    execution_time_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default='running')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    trial: Mapped["Trial"] = relationship()
    retrieval_documents: Mapped[List["RetrievalDocument"]] = relationship(back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        CheckConstraint("status::text = ANY (ARRAY['running'::text, 'completed'::text, 'failed'::text])", name='ck_retrieval_sessions_status'),
        Index("ix_retrieval_sessions_trial_id", "trial_id"),
        Index("ix_retrieval_sessions_session_id", "session_id"),
        Index("ix_retrieval_sessions_status", "status"),
        Index("ix_retrieval_sessions_created_at", "created_at")
    )


class RetrievalDocument(Base):
    """Stores ALL documents found during retrieval for complete audit trail and human verification."""
    __tablename__ = "retrieval_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pmid: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieval_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    retrieval_tier: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # A, B, C, D, E
    query_tier: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # A, B, C, D, E
    policy_engine_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    guardrails_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    retrieval_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    trial: Mapped["Trial"] = relationship()
    session: Mapped[Optional["RetrievalSession"]] = relationship(back_populates="retrieval_documents")
    processed_documents: Mapped[List["ProcessedDocument"]] = relationship(back_populates="retrieval_document", cascade="all, delete-orphan")

    __table_args__ = (
        ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        ForeignKeyConstraint(['session_id'], ['retrieval_sessions.id'], ondelete='SET NULL'),
        CheckConstraint("retrieval_tier::text = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text])", name='ck_retrieval_documents_retrieval_tier'),
        Index("ix_retrieval_documents_trial_id", "trial_id"),
        Index("ix_retrieval_documents_pmid", "pmid"),
        Index("ix_retrieval_documents_retrieval_tier", "retrieval_tier"),
        Index("ix_retrieval_documents_query_tier", "query_tier"),
        Index("ix_retrieval_documents_published_at", "published_at"),
        Index("ix_retrieval_documents_retrieval_score", "retrieval_score")
    )


class ProcessedDocument(Base):
    """Stores only filtered, processed documents ready for LLM processing."""
    __tablename__ = "processed_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trial_id: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_doc_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Link back to retrieval_documents
    pmid: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    r_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    s_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rs_tier: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    entities: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    processing_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    trial: Mapped["Trial"] = relationship()
    retrieval_document: Mapped[Optional["RetrievalDocument"]] = relationship(back_populates="processed_documents")

    __table_args__ = (
        ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        ForeignKeyConstraint(['retrieval_doc_id'], ['retrieval_documents.id'], ondelete='SET NULL'),
        CheckConstraint("rs_tier::text = ANY (ARRAY['R0S0'::text, 'R0S1'::text, 'R1S0'::text, 'R1S1'::text, 'R2S0'::text, 'R2S1'::text, 'R0S2'::text, 'R1S2'::text, 'R2S2'::text, 'R3S0'::text, 'R3S1'::text, 'R3S2'::text, 'R0S3'::text, 'R1S3'::text, 'R2S3'::text, 'R3S3'::text])", name='ck_processed_documents_rs_tier'),
        Index("ix_processed_documents_trial_id", "trial_id"),
        Index("ix_processed_documents_pmid", "pmid"),
        Index("ix_processed_documents_rs_tier", "rs_tier"),
        Index("ix_processed_documents_r_score", "r_score"),
        Index("ix_processed_documents_s_score", "s_score"),
        Index("ix_processed_documents_retrieval_doc_id", "retrieval_doc_id")
    )
