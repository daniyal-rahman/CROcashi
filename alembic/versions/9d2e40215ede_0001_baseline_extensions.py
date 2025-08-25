"""0001 baseline: extensions

Revision ID: 9d2e40215ede
Revises: 
Create Date: 2025-08-24 21:11:46.033799

- Enables pg_trgm extension (used for trigram text search).
- No tables yet; those come in later revisions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d2e40215ede'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure public schema exists (usually true, but harmless)
    op.execute("CREATE SCHEMA IF NOT EXISTS public")

    # Enable trigram extension for fuzzy search on names/aliases later
    # Note: requires appropriate privileges; run as a role that can create extensions.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")

    # Optional: set search_path explicitly if your env uses multiple schemas
    # op.execute("ALTER DATABASE current_database() SET search_path = public")


def downgrade() -> None:
    # Safe rollback: remove the extension (will fail if something depends on it —
    # but at this point we have no dependent objects yet).
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
