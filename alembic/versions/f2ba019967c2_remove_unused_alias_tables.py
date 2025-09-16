"""remove_unused_alias_tables

Revision ID: f2ba019967c2
Revises: 727232fd50ae
Create Date: 2025-09-15 19:21:38.534612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2ba019967c2'
down_revision: Union[str, Sequence[str], None] = '727232fd50ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove unused alias tables (asset_aliases, company_aliases, entity_aliases)."""
    # Drop unused alias tables
    op.drop_table('asset_aliases')
    op.drop_table('company_aliases') 
    op.drop_table('entity_aliases')


def downgrade() -> None:
    """Recreate unused alias tables."""
    from sqlalchemy.dialects import postgresql as psql
    
    # Recreate asset_aliases table
    op.create_table(
        'asset_aliases',
        sa.Column('asset_alias_id', sa.Integer, nullable=False, autoincrement=True),
        sa.Column('asset_id', sa.Integer, nullable=False),
        sa.Column('alias', sa.Text, nullable=False),
        sa.Column('alias_norm', sa.Text, nullable=True),
        sa.Column('alias_type', sa.Text, nullable=False),
        sa.Column('source', sa.Text, nullable=True),
        sa.Column('alias_ascii', sa.Text, nullable=True),
        sa.Column('alias_hyphen_variants', psql.JSONB, nullable=True),
        sa.Column('alias_phonetic', sa.Text, nullable=True),
        sa.Column('alias_fuzzy', psql.JSONB, nullable=True),
        sa.PrimaryKeyConstraint('asset_alias_id'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='CASCADE'),
        sa.CheckConstraint("alias_type::text = ANY (ARRAY['inn','internal_code','generic','brand','misspelling','db_id','code']::text[])", name='ck_asset_aliases_alias_type'),
    )
    op.create_index('ix_asset_aliases_lower_alias', 'asset_aliases', ['alias'])
    op.create_index('ix_asset_aliases_asset_id', 'asset_aliases', ['asset_id'])
    op.create_index('ix_asset_aliases_alias_norm', 'asset_aliases', ['alias_norm'])
    
    # Recreate company_aliases table
    op.create_table(
        'company_aliases',
        sa.Column('alias_id', sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column('company_id', sa.Integer, nullable=False),
        sa.Column('alias', sa.Text, nullable=False),
        sa.Column('source', sa.Text, nullable=True),
        sa.Column('valid_from', sa.Date, nullable=True),
        sa.Column('valid_to', sa.Date, nullable=True),
        sa.Column('alias_norm', sa.Text, nullable=True),
        sa.Column('alias_type', sa.Text, nullable=True),
        sa.PrimaryKeyConstraint('alias_id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
    )
    
    # Recreate entity_aliases table
    op.create_table(
        'entity_aliases',
        sa.Column('id', sa.Integer, nullable=False, autoincrement=True),
        sa.Column('entity_id', sa.Text, nullable=False),
        sa.Column('alias_type', sa.Text, nullable=False),
        sa.Column('alias_value', sa.Text, nullable=False),
        sa.Column('alias_norm', sa.Text, nullable=True),
        sa.Column('confidence', sa.Float, nullable=False, server_default='1.0'),
        sa.Column('is_primary', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['entity_id'], ['entity_packs.entity_id'], ondelete='CASCADE'),
        sa.CheckConstraint("alias_type IN ('asset','company','indication','mechanism','nct_id')", name="ck_entity_aliases_alias_type_valid"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_entity_aliases_confidence_range"),
    )
    op.create_index('ix_entity_aliases_entity_id', 'entity_aliases', ['entity_id'])
    op.create_index('ix_entity_aliases_alias_type', 'entity_aliases', ['alias_type'])
    op.create_index('ix_entity_aliases_alias_value', 'entity_aliases', ['alias_value'])
    op.create_index('ix_entity_aliases_alias_norm', 'entity_aliases', ['alias_norm'])
