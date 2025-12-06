"""
API dependencies.
"""
from typing import Generator

from sqlalchemy.orm import Session

from database.config import get_db_session


def get_db() -> Generator[Session, None, None]:
    """Get database session dependency."""
    with get_db_session() as session:
        yield session

