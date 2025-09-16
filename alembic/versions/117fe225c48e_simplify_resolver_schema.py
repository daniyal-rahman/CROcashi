"""simplify_resolver_schema

Revision ID: 117fe225c48e
Revises: f44bfaf9c8f7
Create Date: 2025-01-27 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '117fe225c48e'
down_revision: Union[str, Sequence[str], None] = 'f44bfaf9c8f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Create simplified resolver tables."""
    
    # 1. Add ticker field to companies table
    op.add_column('companies', sa.Column('ticker', sa.String(10), nullable=True))
    
    # 2. Create academic_blacklist table (more precise than current keyword matching)
    op.create_table(
        'academic_blacklist',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pattern', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 3. Create simplified sponsor_resolutions table
    op.create_table(
        'sponsor_resolutions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nct_id', sa.String(20), nullable=False),
        sa.Column('sponsor_text', sa.Text(), nullable=False),
        sa.Column('sponsor_text_norm', sa.Text(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('match_method', sa.String(20), nullable=False),  # exact, fuzzy, llm, manual
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ),
        sa.UniqueConstraint('nct_id', 'sponsor_text_norm', name='uq_sponsor_resolutions_nct_sponsor')
    )
    
    # 4. Create simplified manual_review_queue table
    op.create_table(
        'manual_review_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nct_id', sa.String(20), nullable=False),
        sa.Column('sponsor_text', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('assigned_company_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['assigned_company_id'], ['companies.company_id'], )
    )
    
    # 5. Create llm_discoveries table (track LLM learning)
    op.create_table(
        'llm_discoveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nct_id', sa.String(20), nullable=False),
        sa.Column('sponsor_text', sa.Text(), nullable=False),
        sa.Column('discovered_company_id', sa.Integer(), nullable=True),
        sa.Column('discovered_aliases', sa.JSON(), nullable=True),  # new aliases found
        sa.Column('llm_response', sa.JSON(), nullable=True),  # full LLM response for learning
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['discovered_company_id'], ['companies.company_id'], )
    )
    
    # 6. Add indexes for performance
    op.create_index('idx_sponsor_resolutions_nct_id', 'sponsor_resolutions', ['nct_id'])
    op.create_index('idx_sponsor_resolutions_company_id', 'sponsor_resolutions', ['company_id'])
    op.create_index('idx_sponsor_resolutions_match_method', 'sponsor_resolutions', ['match_method'])
    op.create_index('idx_manual_review_queue_status', 'manual_review_queue', ['status'])
    op.create_index('idx_manual_review_queue_nct_id', 'manual_review_queue', ['nct_id'])
    op.create_index('idx_llm_discoveries_nct_id', 'llm_discoveries', ['nct_id'])
    op.create_index('idx_llm_discoveries_company_id', 'llm_discoveries', ['discovered_company_id'])
    
    # 7. Add constraints for valid values
    op.create_check_constraint(
        'ck_sponsor_resolutions_match_method',
        'sponsor_resolutions',
        "match_method IN ('exact', 'fuzzy', 'llm', 'manual')"
    )
    op.create_check_constraint(
        'ck_manual_review_queue_status',
        'manual_review_queue',
        "status IN ('pending', 'completed', 'skipped')"
    )
    op.create_check_constraint(
        'ck_sponsor_resolutions_confidence',
        'sponsor_resolutions',
        'confidence >= 0.0 AND confidence <= 1.0'
    )


def downgrade() -> None:
    """Downgrade schema - Remove simplified resolver tables."""
    
    # Drop constraints
    op.drop_constraint('ck_sponsor_resolutions_confidence', 'sponsor_resolutions', type_='check')
    op.drop_constraint('ck_manual_review_queue_status', 'manual_review_queue', type_='check')
    op.drop_constraint('ck_sponsor_resolutions_match_method', 'sponsor_resolutions', type_='check')
    
    # Drop indexes
    op.drop_index('idx_llm_discoveries_company_id', 'llm_discoveries')
    op.drop_index('idx_llm_discoveries_nct_id', 'llm_discoveries')
    op.drop_index('idx_manual_review_queue_nct_id', 'manual_review_queue')
    op.drop_index('idx_manual_review_queue_status', 'manual_review_queue')
    op.drop_index('idx_sponsor_resolutions_match_method', 'sponsor_resolutions')
    op.drop_index('idx_sponsor_resolutions_company_id', 'sponsor_resolutions')
    op.drop_index('idx_sponsor_resolutions_nct_id', 'sponsor_resolutions')
    
    # Drop tables
    op.drop_table('llm_discoveries')
    op.drop_table('manual_review_queue')
    op.drop_table('sponsor_resolutions')
    op.drop_table('academic_blacklist')
    
    # Remove ticker field from companies
    op.drop_column('companies', 'ticker')