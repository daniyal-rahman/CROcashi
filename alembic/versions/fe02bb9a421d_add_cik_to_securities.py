"""add_cik_to_securities

Revision ID: fe02bb9a421d
Revises: 669b4722606d
Create Date: 2025-08-25 18:04:27.362551

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe02bb9a421d'
down_revision: Union[str, Sequence[str], None] = '669b4722606d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add cik column to securities table
    op.add_column('securities', sa.Column('cik', sa.Text(), nullable=True))
    
    # Create index on cik for faster lookups
    op.create_index('idx_securities_cik', 'securities', ['cik'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop index on cik
    op.drop_index('idx_securities_cik', 'securities')
    
    # Drop cik column
    op.drop_column('securities', 'cik')
