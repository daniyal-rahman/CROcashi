"""add_reason_to_review_queue

Revision ID: f5b03315b2de
Revises: 1c483e92fdf0
Create Date: 2025-08-25 21:49:47.822043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5b03315b2de'
down_revision: Union[str, Sequence[str], None] = '1c483e92fdf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add missing reason column to review_queue table
    op.add_column('review_queue', sa.Column('reason', sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the reason column
    op.drop_column('review_queue', 'reason')
