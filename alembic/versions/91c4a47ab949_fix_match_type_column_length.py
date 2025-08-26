"""fix_match_type_column_length

Revision ID: 91c4a47ab949
Revises: 81c4a47ab949
Create Date: 2025-08-26 07:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91c4a47ab949'
down_revision: Union[str, Sequence[str], None] = '81c4a47ab949'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Fix match_type column length in resolver_decisions
    op.alter_column('resolver_decisions', 'match_type',
                    existing_type=sa.String(length=20),
                    type_=sa.String(length=50),
                    existing_nullable=True)
    
    # Fix match_type column length in review_queue
    op.alter_column('review_queue', 'match_type',
                    existing_type=sa.String(length=20),
                    type_=sa.String(length=50),
                    existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert match_type column length in resolver_decisions
    op.alter_column('resolver_decisions', 'match_type',
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=20),
                    existing_nullable=True)
    
    # Revert match_type column length in review_queue
    op.alter_column('review_queue', 'match_type',
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=20),
                    existing_nullable=True)
