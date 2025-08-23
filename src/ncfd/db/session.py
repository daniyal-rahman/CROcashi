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

# Module-level engine and session factory for better connection pooling
_engine = None
_Session = None

def get_engine(url: str | None = None):
    """Return a SQLAlchemy engine bound to the resolved URL."""
    global _engine
    if _engine is None:
        db_url = _get_database_url(url)
        kwargs = {"pool_pre_ping": True, "future": True}
        # SQLite-specific safe defaults
        if db_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(db_url, **kwargs)
    return _engine

def reset_engine():
    """Reset the module-level engine (useful for testing/debugging)."""
    global _engine, _Session
    if _engine:
        try:
            _engine.dispose()
        except Exception:
            pass
    _engine = None
    _Session = None

def create_all(url: str | None = None) -> None:
    """Create all tables defined in :mod:`ncfd.db.models`."""
    engine = get_engine(url)
    Base.metadata.create_all(engine)

# Configure a session factory bound to the module-level engine
def _get_session_factory():
    global _Session
    if _Session is None:
        engine = get_engine()
        _Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return _Session

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
    # Use module-level engine if no URL override
    if url is None:
        session_factory = _get_session_factory()
        session: Session = session_factory()
    else:
        # Fallback to creating new engine for URL override
        engine = create_engine(url, pool_pre_ping=True, future=True)
        session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
        session: Session = session_factory()
    
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
    "reset_engine",
    "create_all",
    "session_scope",
    "get_session",
    "Base",
]
