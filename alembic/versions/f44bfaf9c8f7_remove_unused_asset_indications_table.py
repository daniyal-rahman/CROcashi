"""remove_unused_asset_indications_table

Revision ID: f44bfaf9c8f7
Revises: dd35823d2305
Create Date: 2025-09-15 20:37:30.913435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f44bfaf9c8f7'
down_revision: Union[str, Sequence[str], None] = 'dd35823d2305'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove unused asset_indications table."""
    op.drop_table('asset_indications')


def downgrade() -> None:
    """Recreate asset_indications table."""
    op.create_table(
        'asset_indications',
        sa.Column('asset_id', sa.Integer, nullable=False),
        sa.Column('indication_id', sa.Integer, nullable=False),
        sa.Column('relationship_type', sa.Text, nullable=True),
        sa.Column('evidence_level', sa.Text, nullable=True),
        sa.Column('source', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['indication_id'], ['indication_aliases.indication_id'], ondelete='CASCADE'),
    )
