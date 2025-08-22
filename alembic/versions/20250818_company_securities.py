"""Add company securities table and view

Revision ID: 20250818_company_securities
Revises: 20250818_company_orgs
Create Date: 2025-08-18 10:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250818_company_securities'
down_revision = '20250818_company_orgs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create company_securities link table
    op.create_table('company_securities',
        sa.Column('company_id', sa.BIGINT(), nullable=False),
        sa.Column('security_id', sa.BIGINT(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('company_id', 'security_id')
    )

    # Create view to get company ticker information
    op.execute("""
        CREATE OR REPLACE VIEW v_company_tickers AS
        SELECT
          cs.company_id,
          c.name AS company_name,
          s.ticker,
          s.*
        FROM company_securities cs
        JOIN companies  c ON c.company_id = cs.company_id
        JOIN securities s ON s.id = cs.security_id;
    """)


def downgrade() -> None:
    # Drop the view first
    op.execute('DROP VIEW IF EXISTS v_company_tickers')
    
    # Drop table
    op.drop_table('company_securities')
