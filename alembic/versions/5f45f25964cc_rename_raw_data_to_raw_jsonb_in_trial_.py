"""rename raw_data to raw_jsonb in trial_versions only

Revision ID: 5f45f25964cc
Revises: 0081229f2c27
Create Date: 2025-09-20 11:06:03.618324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '5f45f25964cc'
down_revision: Union[str, Sequence[str], None] = '0081229f2c27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Rename raw_data to raw_jsonb in trial_versions
    op.alter_column('trial_versions', 'raw_data',
               new_column_name='raw_jsonb',
               existing_type=JSONB(),
               existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Rename raw_jsonb back to raw_data in trial_versions
    op.alter_column('trial_versions', 'raw_jsonb',
               new_column_name='raw_data',
               existing_type=JSONB(),
               existing_nullable=False)
