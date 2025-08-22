"""Add company organization tables and views

Revision ID: 20250818_company_orgs
Revises: 7a372ed1b33a
Create Date: 2025-08-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250818_company_orgs'
down_revision = '7a372ed1b33a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Aliases for name/brand normalization
    op.create_table('company_aliases',
        sa.Column('company_id', sa.BIGINT(), nullable=False),
        sa.Column('alias', sa.TEXT(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('company_id', 'alias')
    )
    
    # Create GIN index for trigram search
    op.execute('CREATE INDEX IF NOT EXISTS idx_company_aliases_alias_trgm ON company_aliases USING gin (alias gin_trgm_ops)')

    # 2) Parent/child relationships with dating
    op.create_table('company_relationships',
        sa.Column('parent_company_id', sa.BIGINT(), nullable=False),
        sa.Column('child_company_id', sa.BIGINT(), nullable=False),
        sa.Column('rel_type', sa.TEXT(), nullable=False, server_default='subsidiary'),
        sa.Column('start_date', sa.DATE(), nullable=True),
        sa.Column('end_date', sa.DATE(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['child_company_id'], ['companies.company_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_company_id'], ['companies.company_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('parent_company_id', 'child_company_id', 'rel_type')
    )

    # 3) View to get the ultimate parent ("canonical") for rollups
    op.execute("""
        CREATE OR REPLACE RECURSIVE VIEW v_company_canonical AS
        WITH RECURSIVE up (company_id, canonical_id) AS (
          SELECT c.company_id, c.company_id
          FROM companies c
          WHERE NOT EXISTS (
            SELECT 1 FROM company_relationships r
            WHERE r.child_company_id = c.company_id
              AND r.end_date IS NULL
          )
          UNION
          SELECT r.child_company_id, up.canonical_id
          FROM company_relationships r
          JOIN up ON up.company_id = r.parent_company_id
          WHERE r.end_date IS NULL
        )
        SELECT company_id, canonical_id
        FROM up;
    """)


def downgrade() -> None:
    # Drop the view first
    op.execute('DROP VIEW IF EXISTS v_company_canonical')
    
    # Drop tables
    op.drop_table('company_relationships')
    op.drop_table('company_aliases')
