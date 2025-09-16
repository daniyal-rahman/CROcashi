"""recreate_company_aliases_table

Revision ID: 759550104e16
Revises: 6d9da568e3fd
Create Date: 2025-09-15 20:14:50.050445

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '759550104e16'
down_revision: Union[str, Sequence[str], None] = '6d9da568e3fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Recreate company_aliases table."""
    # Create company_aliases table
    op.create_table(
        'company_aliases',
        sa.Column('alias_id', sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column('company_id', sa.Integer, nullable=False),
        sa.Column('alias', sa.Text, nullable=False),
        sa.Column('alias_norm', sa.Text, nullable=False),
        sa.Column('alias_type', sa.Text, nullable=False),
        sa.Column('source', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('alias_id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        sa.CheckConstraint("alias_type IN ('legal','aka','former_name','short','subsidiary','brand','domain')", name='ck_company_aliases_alias_type_valid'),
    )
    
    # Create indexes for performance
    op.create_index('ix_company_aliases_company_id', 'company_aliases', ['company_id'])
    op.create_index('ix_company_aliases_alias_norm', 'company_aliases', ['alias_norm'])
    op.create_index('ix_company_aliases_alias_type', 'company_aliases', ['alias_type'])
    op.create_index('ix_company_aliases_alias', 'company_aliases', ['alias'])


def downgrade() -> None:
    """Remove company_aliases table."""
    op.drop_table('company_aliases')
