"""add_literature_scoring_and_budget_tables

Revision ID: ff5fabb58e9c
Revises: 6c4909ab66ac
Create Date: 2025-08-27 18:53:47.218853

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ff5fabb58e9c'
down_revision: Union[str, Sequence[str], None] = '6c4909ab66ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    
    # Enums are already created manually to avoid transaction conflicts
    # trial_evaluation_status_enum, budget_period_enum, budget_status_enum, operation_type_enum
    
    # 1. Trial Evaluations Table - Store LLM evaluation results and trial-level posterior probabilities
    op.create_table('trial_evaluations',
        sa.Column('evaluation_id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('trial_id', sa.Integer, sa.ForeignKey('trials.trial_id', ondelete='CASCADE'), nullable=False),
        sa.Column('run_id', sa.Text, nullable=False),  # Links to runs table for lineage tracking
        sa.Column('evaluation_status', postgresql.ENUM('active', 'promoted', 'parked', 'stopped', 'completed', name='trial_evaluation_status_enum', create_type=False), nullable=False, server_default='active'),
        sa.Column('prior_p_short', sa.Numeric(5, 4), nullable=True),  # Prior probability of short trial
        sa.Column('posterior_p_short', sa.Numeric(5, 4), nullable=True),  # Current posterior probability
        sa.Column('llm_evaluation_count', sa.Integer, nullable=False, server_default='0'),  # Number of LLM evaluations performed
        sa.Column('last_evaluation_at', sa.DateTime(timezone=True), nullable=True),  # Timestamp of last LLM evaluation
        sa.Column('evaluation_summary', sa.Text, nullable=True),  # Summary of LLM evaluation results
        sa.Column('metadata_jsonb', postgresql.JSONB, nullable=True),  # Additional metadata from evaluations
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )
    
    # 2. Document Utilities Table - Store U0 and U1 scores for documents
    op.create_table('document_utilities',
        sa.Column('utility_id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('doc_id', sa.Integer, sa.ForeignKey('documents.doc_id', ondelete='CASCADE'), nullable=False),
        sa.Column('trial_id', sa.Integer, sa.ForeignKey('trials.trial_id', ondelete='CASCADE'), nullable=False),
        sa.Column('run_id', sa.Text, nullable=False),  # Links to runs table for lineage tracking
        sa.Column('u0_score', sa.Numeric(5, 4), nullable=False),  # Metadata-only utility score (0-1)
        sa.Column('u1_score', sa.Numeric(5, 4), nullable=True),  # Abstract-based utility score (0-1)
        sa.Column('uncertainty', sa.Numeric(5, 4), nullable=True),  # Uncertainty in U1 score
        sa.Column('scoring_metadata', postgresql.JSONB, nullable=True),  # Detailed scoring breakdown
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )
    
    # 3. Trial Priority Queue Table - Store trial priority and status information
    op.create_table('trial_priority_queue',
        sa.Column('queue_id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('trial_id', sa.Integer, sa.ForeignKey('trials.trial_id', ondelete='CASCADE'), nullable=False),
        sa.Column('run_id', sa.Text, nullable=False),  # Links to runs table for lineage tracking
        sa.Column('priority_score', sa.Numeric(10, 6), nullable=False),  # Computed priority score
        sa.Column('queue_status', postgresql.ENUM('active', 'promoted', 'parked', 'stopped', 'completed', name='trial_evaluation_status_enum', create_type=False), nullable=False, server_default='active'),
        sa.Column('last_processed_at', sa.DateTime(timezone=True), nullable=True),  # When trial was last processed
        sa.Column('processing_stage', sa.Text, nullable=True),  # Current stage: 'stage_a', 'stage_b', 'stage_c'
        sa.Column('stage_a_completed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('stage_b_completed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('stage_c_completed', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('queue_metadata', postgresql.JSONB, nullable=True),  # Additional queue management data
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )
    
    # 4. Cost Tracking Table - Store budget monitoring data
    op.create_table('cost_records',
        sa.Column('cost_id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('transaction_id', sa.Text, nullable=False),  # Unique transaction identifier
        sa.Column('trial_id', sa.Integer, sa.ForeignKey('trials.trial_id', ondelete='CASCADE'), nullable=False),
        sa.Column('run_id', sa.Text, nullable=False),  # Links to runs table for lineage tracking
        sa.Column('operation_type', postgresql.ENUM('metadata_fetch', 'abstract_fetch', 'full_text_fetch', 'llm_evaluation', name='operation_type_enum', create_type=False), nullable=False),
        sa.Column('cost_amount', sa.Numeric(10, 6), nullable=False),  # Cost in dollars
        sa.Column('operation_metadata', postgresql.JSONB, nullable=True),  # Additional operation details
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    )
    
    # 5. Budget Periods Table - Store budget period information and limits
    op.create_table('budget_periods',
        sa.Column('period_id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('period_type', postgresql.ENUM('daily', 'weekly', 'monthly', name='budget_period_enum', create_type=False), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('daily_limit', sa.Numeric(10, 2), nullable=False),  # Daily cost limit
        sa.Column('monthly_limit', sa.Numeric(10, 2), nullable=False),  # Monthly cost limit
        sa.Column('trial_limit', sa.Numeric(10, 2), nullable=False),  # Per-trial cost limit
        sa.Column('total_spent', sa.Numeric(10, 2), nullable=False, server_default='0.00'),  # Total spent in period
        sa.Column('status', postgresql.ENUM('ok', 'warning', 'critical', 'emergency', 'exceeded', name='budget_status_enum', create_type=False), nullable=False, server_default='ok'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)
    )
    
    # Create indexes for performance
    # Trial evaluations
    op.create_index('idx_trial_evaluations_trial_id', 'trial_evaluations', ['trial_id'])
    op.create_index('idx_trial_evaluations_run_id', 'trial_evaluations', ['run_id'])
    op.create_index('idx_trial_evaluations_status', 'trial_evaluations', ['evaluation_status'])
    op.create_index('idx_trial_evaluations_posterior', 'trial_evaluations', ['posterior_p_short'])
    
    # Document utilities
    op.create_index('idx_document_utilities_doc_id', 'document_utilities', ['doc_id'])
    op.create_index('idx_document_utilities_trial_id', 'document_utilities', ['trial_id'])
    op.create_index('idx_document_utilities_run_id', 'document_utilities', ['run_id'])
    op.create_index('idx_document_utilities_u0_score', 'document_utilities', ['u0_score'])
    op.create_index('idx_document_utilities_u1_score', 'document_utilities', ['u1_score'])
    op.create_index('idx_document_utilities_combined_score', 'document_utilities', ['trial_id', 'u0_score', 'u1_score'])
    
    # Trial priority queue
    op.create_index('idx_trial_priority_queue_trial_id', 'trial_priority_queue', ['trial_id'])
    op.create_index('idx_trial_priority_queue_run_id', 'trial_priority_queue', ['run_id'])
    op.create_index('idx_trial_priority_queue_priority', 'trial_priority_queue', ['priority_score'])
    op.create_index('idx_trial_priority_queue_status', 'trial_priority_queue', ['queue_status'])
    op.create_index('idx_trial_priority_queue_stage', 'trial_priority_queue', ['processing_stage'])
    op.create_index('idx_trial_priority_queue_active', 'trial_priority_queue', ['queue_status', 'priority_score'])
    
    # Cost records
    op.create_index('idx_cost_records_trial_id', 'cost_records', ['trial_id'])
    op.create_index('idx_cost_records_run_id', 'cost_records', ['run_id'])
    op.create_index('idx_cost_records_operation_type', 'cost_records', ['operation_type'])
    op.create_index('idx_cost_records_recorded_at', 'cost_records', ['recorded_at'])
    op.create_index('idx_cost_records_transaction_id', 'cost_records', ['transaction_id'], unique=True)
    
    # Budget periods
    op.create_index('idx_budget_periods_type_start', 'budget_periods', ['period_type', 'period_start'])
    op.create_index('idx_budget_periods_status', 'budget_periods', ['status'])
    op.create_index('idx_budget_periods_current', 'budget_periods', ['period_type', 'period_start', 'period_end'])
    
    # Create unique constraints
    op.create_unique_constraint('uq_trial_evaluations_trial_run', 'trial_evaluations', ['trial_id', 'run_id'])
    op.create_unique_constraint('uq_document_utilities_doc_trial_run', 'document_utilities', ['doc_id', 'trial_id', 'run_id'])
    op.create_unique_constraint('uq_trial_priority_queue_trial_run', 'trial_priority_queue', ['trial_id', 'run_id'])
    op.create_unique_constraint('uq_budget_periods_type_start', 'budget_periods', ['period_type', 'period_start'])
    
    # Create check constraints
    op.create_check_constraint('ck_trial_evaluations_prior_range', 'trial_evaluations', 'prior_p_short BETWEEN 0 AND 1')
    op.create_check_constraint('ck_trial_evaluations_posterior_range', 'trial_evaluations', 'posterior_p_short BETWEEN 0 AND 1')
    op.create_check_constraint('ck_document_utilities_u0_range', 'document_utilities', 'u0_score BETWEEN 0 AND 1')
    op.create_check_constraint('ck_document_utilities_u1_range', 'document_utilities', 'u1_score BETWEEN 0 AND 1 OR u1_score IS NULL')
    op.create_check_constraint('ck_document_utilities_uncertainty_range', 'document_utilities', 'uncertainty BETWEEN 0 AND 1 OR uncertainty IS NULL')
    op.create_check_constraint('ck_cost_records_amount_positive', 'cost_records', 'cost_amount > 0')
    op.create_check_constraint('ck_budget_periods_limits_positive', 'budget_periods', 'daily_limit > 0 AND monthly_limit > 0 AND trial_limit > 0')
    op.create_check_constraint('ck_budget_periods_spent_positive', 'budget_periods', 'total_spent >= 0')


def downgrade() -> None:
    """Downgrade schema."""
    
    # Drop tables in reverse order
    op.drop_table('budget_periods')
    op.drop_table('cost_records')
    op.drop_table('trial_priority_queue')
    op.drop_table('document_utilities')
    op.drop_table('trial_evaluations')
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS operation_type_enum")
    op.execute("DROP TYPE IF EXISTS budget_status_enum")
    op.execute("DROP TYPE IF EXISTS budget_period_enum")
    op.execute("DROP TYPE IF EXISTS trial_evaluation_status_enum")
