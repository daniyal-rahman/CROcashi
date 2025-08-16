"""Database session helpers."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def get_engine(url: str | None = None):
    """Return a SQLAlchemy engine.

    Parameters
    ----------
    url:
        Database URL. If ``None`` the ``DATABASE_URL`` environment variable is
        used. When neither is provided an in-memory SQLite database is used
        which is suitable for tests.
    """

    return create_engine(url or os.getenv("DATABASE_URL", "sqlite+pysqlite:///:memory:"))


def create_all(url: str | None = None) -> None:
    """Create all tables defined in :mod:`ncfd.db.models`."""

    engine = get_engine(url)
    Base.metadata.create_all(engine)


SessionLocal = sessionmaker(autocommit=False, autoflush=False)


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""

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


__all__ = ["get_engine", "create_all", "session_scope", "SessionLocal", "Base"]

