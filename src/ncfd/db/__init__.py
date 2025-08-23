# Re-export session helpers so callers can do: from ncfd.db import get_session
from .session import (
    get_engine,
    create_all,
    session_scope,
    get_session,
    Base,
)

# Optional: provide a module-level engine for code that expects `from ncfd.db import engine`
# It uses the same env-driven URL resolution as session.py
engine = get_engine()

__all__ = [
    "engine",
    "get_engine",
    "create_all",
    "session_scope",
    "get_session",
    "Base",
]
