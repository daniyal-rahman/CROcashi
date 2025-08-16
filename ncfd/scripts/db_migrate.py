"""Helper script to run Alembic migrations."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade(revision: str = "head") -> None:
    """Upgrade the database to ``revision`` (defaults to ``head``)."""

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(cfg, revision)


if __name__ == "__main__":  # pragma: no cover - convenience entry point
    upgrade()

