"""Database session helpers."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

# -----------------------------------------------------------------------------
# Engine / URL helpers
# -----------------------------------------------------------------------------

def _get_database_url(override: Optional[str] = None) -> str:
    """
    Resolve the database URL with sensible fallbacks:
      1) explicit override (argument)
      2) env: DATABASE_URL
      3) env: POSTGRES_DSN   (compat with other modules)
      4) in-memory SQLite (tests)
    """
    return (
        override
        or os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_DSN")
        or "sqlite+pysqlite:///:memory:"
    )

def get_engine(url: str | None = None):
    """Return a SQLAlchemy engine bound to the resolved URL."""
    db_url = _get_database_url(url)
    kwargs = {"pool_pre_ping": True, "future": True}
    # SQLite-specific safe defaults
    if db_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(db_url, **kwargs)

def create_all(url: str | None = None) -> None:
    """Create all tables defined in :mod:`ncfd.db.models`."""
    engine = get_engine(url)
    Base.metadata.create_all(engine)

# Configure an unbound Session factory; we bind per-context to chosen engine.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, future=True)

# -----------------------------------------------------------------------------
# Context managers
# -----------------------------------------------------------------------------

@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    """
    Provide a transactional scope around a series of operations.

    Usage:
        with session_scope() as s:
            s.execute(...)
    """
    engine = get_engine(url)
    SessionLocal.configure(bind=engine)
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

@contextmanager
def get_session(url: str | None = None) -> Iterator[Session]:
    """
    Alias of session_scope() for modules/CLIs that expect get_session().
    Resolves DATABASE_URL/POSTGRES_DSN automatically if url is not provided.
    """
    with session_scope(url=url) as s:
        yield s

__all__ = [
    "get_engine",
    "create_all",
    "session_scope",
    "get_session",
    "SessionLocal",
    "Base",
]
