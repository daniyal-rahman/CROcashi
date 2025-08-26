"""add_resolver_tables

Revision ID: 03fdbe8b0719
Revises: b2343cc60db5
Create Date: 2025-08-25 18:28:19.920767

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '03fdbe8b0719'
down_revision: Union[str, Sequence[str], None] = 'b2343cc60db5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create resolver_features table
    op.create_table(
        'resolver_features',
        sa.Column('run_id', sa.String(length=50), nullable=False),
        sa.Column('nct_id', sa.String(length=20), nullable=False),
        sa.Column('sponsor_text_norm', sa.String(length=200), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('features_jsonb', sa.JSON(), nullable=True),
        sa.Column('score_precal', sa.Float(), nullable=True),
        sa.Column('p_calibrated', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('run_id', 'nct_id', 'sponsor_text_norm', 'company_id')
    )
    
    # Create resolver_decisions table
    op.create_table(
        'resolver_decisions',
        sa.Column('run_id', sa.String(length=50), nullable=False),
        sa.Column('nct_id', sa.String(length=20), nullable=False),
        sa.Column('sponsor_text', sa.String(length=500), nullable=False),
        sa.Column('sponsor_text_norm', sa.String(length=200), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('match_type', sa.String(length=20), nullable=True),
        sa.Column('p_match', sa.Float(), nullable=True),
        sa.Column('top2_margin', sa.Float(), nullable=True),
        sa.Column('features_jsonb', sa.JSON(), nullable=True),
        sa.Column('evidence_jsonb', sa.JSON(), nullable=True),
        sa.Column('decided_by', sa.String(length=20), nullable=False),
        sa.Column('notes_md', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('run_id', 'nct_id', 'sponsor_text_norm')
    )
    
    # Create review_queue table
    op.create_table(
        'review_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=50), nullable=False),
        sa.Column('nct_id', sa.String(length=20), nullable=False),
        sa.Column('sponsor_text', sa.String(length=500), nullable=False),
        sa.Column('sponsor_text_norm', sa.String(length=200), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('match_type', sa.String(length=20), nullable=True),
        sa.Column('p_match', sa.Float(), nullable=True),
        sa.Column('top2_margin', sa.Float(), nullable=True),
        sa.Column('features_jsonb', sa.JSON(), nullable=True),
        sa.Column('evidence_jsonb', sa.JSON(), nullable=True),
        sa.Column('decided_by', sa.String(length=20), nullable=False),
        sa.Column('notes_md', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for better performance
    op.create_index('idx_resolver_features_run_id', 'resolver_features', ['run_id'])
    op.create_index('idx_resolver_features_nct_id', 'resolver_features', ['nct_id'])
    op.create_index('idx_resolver_decisions_run_id', 'resolver_decisions', ['run_id'])
    op.create_index('idx_resolver_decisions_nct_id', 'resolver_decisions', ['nct_id'])
    op.create_index('idx_review_queue_status', 'review_queue', ['status'])
    op.create_index('idx_review_queue_nct_id', 'review_queue', ['nct_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_review_queue_nct_id', 'review_queue')
    op.drop_index('idx_review_queue_status', 'review_queue')
    op.drop_index('idx_resolver_decisions_nct_id', 'resolver_decisions')
    op.drop_index('idx_resolver_decisions_run_id', 'resolver_decisions')
    op.drop_index('idx_resolver_features_nct_id', 'resolver_features')
    op.drop_index('idx_resolver_features_run_id', 'resolver_features')
    
    # Drop tables
    op.drop_table('review_queue')
    op.drop_table('resolver_decisions')
    op.drop_table('resolver_features')
