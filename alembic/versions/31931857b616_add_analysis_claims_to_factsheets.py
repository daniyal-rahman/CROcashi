"""add_analysis_claims_to_factsheets

Revision ID: 31931857b616
Revises: 903237fab6ce
Create Date: 2025-09-24 20:56:24.258935

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '31931857b616'
down_revision: Union[str, Sequence[str], None] = '903237fab6ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add analysis_claims JSONB column to factsheets table
    op.add_column('factsheets', sa.Column('analysis_claims', postgresql.JSONB(), nullable=True))
    # Set default value for existing rows
    op.execute("UPDATE factsheets SET analysis_claims = '[]'::jsonb WHERE analysis_claims IS NULL")
    # Set default for new rows
    op.alter_column('factsheets', 'analysis_claims', server_default=sa.text("'[]'::jsonb"))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove analysis_claims column from factsheets table
    op.drop_column('factsheets', 'analysis_claims')
