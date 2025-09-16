"""simplify_asset_ownership_to_one_to_one

Revision ID: dd35823d2305
Revises: d4161c888dbf
Create Date: 2025-09-15 20:33:29.763507

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd35823d2305'
down_revision: Union[str, Sequence[str], None] = 'd4161c888dbf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Simplify asset ownership from many-to-many to one-to-one."""
    # Step 1: Add new ownership columns to assets table
    op.add_column('assets', sa.Column('owner_company_id', sa.Integer(), nullable=True))
    op.add_column('assets', sa.Column('ownership_history', sa.JSON(), nullable=True))
    
    # Step 2: Add foreign key constraint
    op.create_foreign_key('fk_assets_owner_company', 'assets', 'companies', ['owner_company_id'], ['company_id'])
    
    # Step 3: Add index for performance
    op.create_index('ix_assets_owner_company_id', 'assets', ['owner_company_id'])
    
    # Step 4: Drop the asset_ownership table
    op.drop_table('asset_ownership')


def downgrade() -> None:
    """Revert to many-to-many asset ownership."""
    # Step 4: Recreate asset_ownership table
    op.create_table(
        'asset_ownership',
        sa.Column('ownership_id', sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column('asset_id', sa.Integer, nullable=False),
        sa.Column('company_id', sa.Integer, nullable=False),
        sa.Column('start_date', sa.Date, nullable=True),
        sa.Column('end_date', sa.Date, nullable=True),
        sa.Column('source', sa.Text, nullable=False),
        sa.Column('evidence_url', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('ownership_id'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
    )
    
    # Recreate indexes
    op.create_index('idx_asset_ownership_asset_id', 'asset_ownership', ['asset_id'])
    op.create_index('idx_asset_ownership_company_id', 'asset_ownership', ['company_id'])
    op.create_index('idx_asset_ownership_start_date', 'asset_ownership', ['start_date'])
    
    # Step 3: Drop index
    op.drop_index('ix_assets_owner_company_id', 'assets')
    
    # Step 2: Drop foreign key constraint
    op.drop_constraint('fk_assets_owner_company', 'assets', type_='foreignkey')
    
    # Step 1: Remove new columns from assets table
    op.drop_column('assets', 'ownership_history')
    op.drop_column('assets', 'owner_company_id')
