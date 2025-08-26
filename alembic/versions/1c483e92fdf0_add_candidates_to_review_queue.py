"""complete_resolver_schema

Revision ID: 1c483e92fdf0
Revises: 03fdbe8b0719
Create Date: 2025-08-25 21:41:01.886281

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c483e92fdf0'
down_revision: Union[str, Sequence[str], None] = '03fdbe8b0719'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add missing candidates column to review_queue table
    op.add_column('review_queue', sa.Column('candidates', sa.JSON(), nullable=True))
    
    # Add missing columns to existing resolver_features table
    op.add_column('resolver_features', sa.Column('input_id', sa.Integer(), nullable=True))
    op.add_column('resolver_features', sa.Column('source_mask', sa.Integer(), nullable=True))
    op.add_column('resolver_features', sa.Column('score_logit', sa.Float(), nullable=True))
    op.add_column('resolver_features', sa.Column('rank_order', sa.Integer(), nullable=True))
    op.add_column('resolver_features', sa.Column('top2_margin', sa.Float(), nullable=True))
    
    # Add missing columns to existing resolver_decisions table
    op.add_column('resolver_decisions', sa.Column('input_id', sa.Integer(), nullable=True))
    op.add_column('resolver_decisions', sa.Column('outcome', sa.String(length=20), nullable=True))
    op.add_column('resolver_decisions', sa.Column('decider', sa.String(length=20), nullable=True))
    op.add_column('resolver_decisions', sa.Column('posterior_probability', sa.Float(), nullable=True))
    
    # Add missing columns to existing review_queue table
    op.add_column('review_queue', sa.Column('input_id', sa.Integer(), nullable=True))
    op.add_column('review_queue', sa.Column('suggested_company', sa.Integer(), nullable=True))
    op.add_column('review_queue', sa.Column('assigned_to', sa.String(length=100), nullable=True))
    
    # Create new tables
    
    # 1. Runs table
    op.create_table(
        'resolver_runs',
        sa.Column('run_id', sa.String(length=50), nullable=False),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('ended_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('decider', sa.String(length=20), nullable=False),
        sa.Column('config_hash', sa.String(length=64), nullable=True),
        sa.Column('config_notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('run_id')
    )
    
    # 2. Inputs table
    op.create_table(
        'resolver_inputs',
        sa.Column('input_id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=50), nullable=False),
        sa.Column('nct_id', sa.String(length=20), nullable=False),
        sa.Column('sponsor_text', sa.String(length=500), nullable=False),
        sa.Column('sponsor_text_norm_strict', sa.String(length=200), nullable=False),
        sa.Column('sponsor_text_norm_loose', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('input_id'),
        sa.ForeignKeyConstraint(['run_id'], ['resolver_runs.run_id'], ondelete='CASCADE')
    )
    
    # 3. Deterministic Rules table
    op.create_table(
        'resolver_rules',
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('pattern', sa.String(length=500), nullable=False),
        sa.Column('match_mode', sa.String(length=20), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('rule_id')
    )
    
    # 4. Overrides table
    op.create_table(
        'resolver_overrides',
        sa.Column('override_id', sa.Integer(), nullable=False),
        sa.Column('nct_id', sa.String(length=20), nullable=False),
        sa.Column('sponsor_text', sa.String(length=500), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('reason_md', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.PrimaryKeyConstraint('override_id')
    )
    
    # 5. LLM Logs table
    op.create_table(
        'resolver_llm_logs',
        sa.Column('llm_log_id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=50), nullable=False),
        sa.Column('input_id', sa.Integer(), nullable=True),
        sa.Column('stage', sa.String(length=50), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('response', sa.Text(), nullable=False),
        sa.Column('token_count_input', sa.Integer(), nullable=True),
        sa.Column('token_count_output', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('llm_log_id'),
        sa.ForeignKeyConstraint(['run_id'], ['resolver_runs.run_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['input_id'], ['resolver_inputs.input_id'], ondelete='CASCADE')
    )
    
    # 6. Raw Candidate Snapshots table
    op.create_table(
        'resolver_candidate_snapshots',
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=50), nullable=False),
        sa.Column('input_id', sa.Integer(), nullable=True),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('alias_id', sa.Integer(), nullable=True),
        sa.Column('retrieval_stage', sa.String(length=50), nullable=False),
        sa.Column('signal', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('candidate_id'),
        sa.ForeignKeyConstraint(['run_id'], ['resolver_runs.run_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['input_id'], ['resolver_inputs.input_id'], ondelete='CASCADE')
    )
    
    # Create indexes for better performance
    op.create_index('idx_resolver_inputs_run_id', 'resolver_inputs', ['run_id'])
    op.create_index('idx_resolver_inputs_nct_id', 'resolver_inputs', ['nct_id'])
    op.create_index('idx_resolver_rules_priority', 'resolver_rules', ['priority'])
    op.create_index('idx_resolver_rules_enabled', 'resolver_rules', ['enabled'])
    op.create_index('idx_resolver_overrides_nct_id', 'resolver_overrides', ['nct_id'])
    op.create_index('idx_resolver_overrides_active', 'resolver_overrides', ['active'])
    op.create_index('idx_resolver_llm_logs_run_id', 'resolver_llm_logs', ['run_id'])
    op.create_index('idx_resolver_llm_logs_stage', 'resolver_llm_logs', ['stage'])
    op.create_index('idx_resolver_candidate_snapshots_run_id', 'resolver_candidate_snapshots', ['run_id'])
    op.create_index('idx_resolver_candidate_snapshots_retrieval_stage', 'resolver_candidate_snapshots', ['retrieval_stage'])
    
    # Add foreign key constraints for existing tables
    op.create_foreign_key('fk_resolver_features_input_id', 'resolver_features', 'resolver_inputs', ['input_id'], ['input_id'])
    op.create_foreign_key('fk_resolver_decisions_input_id', 'resolver_decisions', 'resolver_inputs', ['input_id'], ['input_id'])
    op.create_foreign_key('fk_review_queue_input_id', 'review_queue', 'resolver_inputs', ['input_id'], ['input_id'])
    op.create_foreign_key('fk_review_queue_suggested_company', 'review_queue', 'companies', ['suggested_company'], ['company_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop foreign key constraints for existing tables
    op.drop_constraint('fk_review_queue_suggested_company', 'review_queue', type_='foreignkey')
    op.drop_constraint('fk_review_queue_input_id', 'review_queue', type_='foreignkey')
    op.drop_constraint('fk_resolver_decisions_input_id', 'resolver_decisions', type_='foreignkey')
    op.drop_constraint('fk_resolver_features_input_id', 'resolver_features', type_='foreignkey')
    
    # Drop indexes
    op.drop_index('idx_resolver_candidate_snapshots_retrieval_stage', 'resolver_candidate_snapshots')
    op.drop_index('idx_resolver_candidate_snapshots_run_id', 'resolver_candidate_snapshots')
    op.drop_index('idx_resolver_llm_logs_stage', 'resolver_llm_logs')
    op.drop_index('idx_resolver_llm_logs_run_id', 'resolver_llm_logs')
    op.drop_index('idx_resolver_overrides_active', 'resolver_overrides')
    op.drop_index('idx_resolver_overrides_nct_id', 'resolver_overrides')
    op.drop_index('idx_resolver_rules_enabled', 'resolver_rules')
    op.drop_index('idx_resolver_rules_priority', 'resolver_rules')
    op.drop_index('idx_resolver_inputs_nct_id', 'resolver_inputs')
    op.drop_index('idx_resolver_inputs_run_id', 'resolver_inputs')
    
    # Drop new tables
    op.drop_table('resolver_candidate_snapshots')
    op.drop_table('resolver_llm_logs')
    op.drop_table('resolver_overrides')
    op.drop_table('resolver_rules')
    op.drop_table('resolver_inputs')
    op.drop_table('resolver_runs')
    
    # Drop added columns from existing tables
    op.drop_column('review_queue', 'assigned_to')
    op.drop_column('review_queue', 'suggested_company')
    op.drop_column('review_queue', 'input_id')
    op.drop_column('resolver_decisions', 'posterior_probability')
    op.drop_column('resolver_decisions', 'decider')
    op.drop_column('resolver_decisions', 'outcome')
    op.drop_column('resolver_decisions', 'input_id')
    op.drop_column('resolver_features', 'top2_margin')
    op.drop_column('resolver_features', 'rank_order')
    op.drop_column('resolver_features', 'score_logit')
    op.drop_column('resolver_features', 'source_mask')
    op.drop_column('resolver_features', 'input_id')
    op.drop_column('review_queue', 'candidates')
