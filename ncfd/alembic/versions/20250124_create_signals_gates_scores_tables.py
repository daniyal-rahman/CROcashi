"""Create signals, gates, and scores tables

This migration creates the core tables for the signals and gates system:
1. signals table for storing signal data
2. gates table for defining validation gates
3. scores table for storing computed scores

Revision ID: 20250124_signals_gates_scores
Revises: 20250123_add_link_audit_fields
Create Date: 2025-01-24 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250124_signals_gates_scores'
down_revision = '20250123_add_link_audit_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create signals, gates, and scores tables with idempotent operations."""
    
    # Check if tables already exist to make migration idempotent
    def table_exists(table_name: str) -> bool:
        connection = op.get_bind()
        result = connection.execute(
            sa.text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"),
            {"table_name": table_name}
        ).scalar()
        return result
    
    def index_exists(index_name: str) -> bool:
        connection = op.get_bind()
        result = connection.execute(
            sa.text("SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = :index_name)"),
            {"index_name": index_name}
        ).scalar()
        return result
    
    def constraint_exists(constraint_name: str) -> bool:
        connection = op.get_bind()
        result = connection.execute(
            sa.text("SELECT EXISTS (SELECT FROM information_schema.table_constraints WHERE constraint_name = :constraint_name)"),
            {"constraint_name": constraint_name}
        ).scalar()
        return result

    # Create signals table
    if not table_exists("signals"):
        op.create_table(
            'signals',
            sa.Column('signal_id', sa.BigInteger(), nullable=False),
            sa.Column('trial_id', sa.BigInteger(), nullable=False),
            sa.Column('S_id', sa.String(length=10), nullable=False),  # S1, S2, S3, etc.
            sa.Column('value', sa.Numeric(precision=10, scale=6), nullable=True),  # Numeric signal value
            sa.Column('severity', sa.String(length=1), nullable=False),  # H, M, L
            sa.Column('evidence_span', sa.Text(), nullable=True),  # JSON or text describing evidence
            sa.Column('source_study_id', sa.BigInteger(), nullable=True),  # Reference to studies table
            sa.Column('fired_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
            sa.PrimaryKeyConstraint('signal_id'),
            sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['source_study_id'], ['studies.study_id'], ondelete='SET NULL'),
            sa.CheckConstraint("severity IN ('H', 'M', 'L')", name='ck_signals_severity_valid'),
            sa.CheckConstraint("\"S_id\" ~ '^S[1-9]$'", name='ck_signals_s_id_format'),
            sa.CheckConstraint("value IS NULL OR (value >= -999999.999999 AND value <= 999999.999999)", name='ck_signals_value_range')
        )
        
        # Create indexes for signals table
        op.create_index('ix_signals_trial_id', 'signals', ['trial_id'])
        op.create_index('ix_signals_s_id', 'signals', ['S_id'])
        op.create_index('ix_signals_severity', 'signals', ['severity'])
        op.create_index('ix_signals_fired_at', 'signals', ['fired_at'])
        op.create_index('ix_signals_trial_s_id', 'signals', ['trial_id', 'S_id'], unique=True)
        op.create_index('ix_signals_metadata_gin', 'signals', ['metadata'], postgresql_using='gin')
    
    # Create gates table
    if not table_exists("gates"):
        op.create_table(
            'gates',
            sa.Column('gate_id', sa.BigInteger(), nullable=False),
            sa.Column('trial_id', sa.BigInteger(), nullable=False),
            sa.Column('G_id', sa.String(length=10), nullable=False),  # G1, G2, G3, G4
            sa.Column('fired_bool', sa.Boolean(), nullable=False, default=False),
            sa.Column('supporting_S_ids', postgresql.ARRAY(sa.String(length=10)), nullable=True),  # Array of S_ids
            sa.Column('lr_used', sa.Numeric(precision=10, scale=6), nullable=True),  # Likelihood ratio
            sa.Column('rationale_text', sa.Text(), nullable=True),  # Human-readable explanation
            sa.Column('evaluated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
            sa.PrimaryKeyConstraint('gate_id'),
            sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
            sa.CheckConstraint("\"G_id\" ~ '^G[1-4]$'", name='ck_gates_g_id_format'),
            sa.CheckConstraint("lr_used IS NULL OR (lr_used >= 0 AND lr_used <= 999999.999999)", name='ck_gates_lr_range')
        )
        
        # Create indexes for gates table
        op.create_index('ix_gates_trial_id', 'gates', ['trial_id'])
        op.create_index('ix_gates_g_id', 'gates', ['G_id'])
        op.create_index('ix_gates_fired_bool', 'gates', ['fired_bool'])
        op.create_index('ix_gates_trial_g_id', 'gates', ['trial_id', 'G_id'], unique=True)
        op.create_index('ix_gates_metadata_gin', 'gates', ['metadata'], postgresql_using='gin')
    
    # Create scores table
    if not table_exists("scores"):
        op.create_table(
            'scores',
            sa.Column('score_id', sa.BigInteger(), nullable=False),
            sa.Column('trial_id', sa.BigInteger(), nullable=False),
            sa.Column('run_id', sa.String(length=50), nullable=False),  # Unique identifier for scoring run
            sa.Column('prior_pi', sa.Numeric(precision=6, scale=5), nullable=False),  # Prior failure probability
            sa.Column('logit_prior', sa.Numeric(precision=10, scale=6), nullable=False),  # log(prior_pi/(1-prior_pi))
            sa.Column('sum_log_lr', sa.Numeric(precision=10, scale=6), nullable=False, default=0),  # Sum of log likelihood ratios
            sa.Column('logit_post', sa.Numeric(precision=10, scale=6), nullable=False),  # logit_prior + sum_log_lr
            sa.Column('p_fail', sa.Numeric(precision=6, scale=5), nullable=False),  # Posterior failure probability
            sa.Column('features_frozen_at', sa.DateTime(timezone=True), nullable=True),  # When features were frozen
            sa.Column('scored_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
            sa.PrimaryKeyConstraint('score_id'),
            sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
            sa.CheckConstraint("prior_pi >= 0 AND prior_pi <= 1", name='ck_scores_prior_pi_range'),
            sa.CheckConstraint("p_fail >= 0 AND p_fail <= 1", name='ck_scores_p_fail_range'),
            sa.CheckConstraint("logit_prior >= -20 AND logit_prior <= 20", name='ck_scores_logit_prior_range'),
            sa.CheckConstraint("logit_post >= -20 AND logit_post <= 20", name='ck_scores_logit_post_range'),
            sa.CheckConstraint("sum_log_lr >= -20 AND sum_log_lr <= 20", name='ck_scores_sum_log_lr_range')
        )
        
        # Create indexes for scores table
        op.create_index('ix_scores_trial_id', 'scores', ['trial_id'])
        op.create_index('ix_scores_run_id', 'scores', ['run_id'])
        op.create_index('ix_scores_p_fail', 'scores', ['p_fail'])
        op.create_index('ix_scores_scored_at', 'scores', ['scored_at'])
        op.create_index('ix_scores_trial_run', 'scores', ['trial_id', 'run_id'], unique=True)
        op.create_index('ix_scores_metadata_gin', 'scores', ['metadata'], postgresql_using='gin')
    
    # Create trial_versions table if it doesn't exist (needed for S1 endpoint change detection)
    if not table_exists("trial_versions"):
        op.create_table(
            'trial_versions',
            sa.Column('version_id', sa.BigInteger(), nullable=False),
            sa.Column('trial_id', sa.BigInteger(), nullable=False),
            sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('raw_jsonb', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
            sa.Column('primary_endpoint_text', sa.Text(), nullable=True),
            sa.Column('sample_size', sa.Integer(), nullable=True),
            sa.Column('analysis_plan_text', sa.Text(), nullable=True),
            sa.Column('changes_jsonb', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
            sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
            sa.PrimaryKeyConstraint('version_id'),
            sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
            sa.CheckConstraint("sample_size IS NULL OR sample_size > 0", name='ck_trial_versions_sample_size_positive')
        )
        
        # Create indexes for trial_versions table
        op.create_index('ix_trial_versions_trial_id', 'trial_versions', ['trial_id'])
        op.create_index('ix_trial_versions_captured_at', 'trial_versions', ['captured_at'])
        op.create_index('ix_trial_versions_raw_jsonb_gin', 'trial_versions', ['raw_jsonb'], postgresql_using='gin')
        op.create_index('ix_trial_versions_changes_jsonb_gin', 'trial_versions', ['changes_jsonb'], postgresql_using='gin')
        op.create_index('ix_trial_versions_metadata_gin', 'trial_versions', ['metadata'], postgresql_using='gin')


def downgrade() -> None:
    """Drop signals, gates, scores, and trial_versions tables."""
    
    # Drop tables in reverse order due to foreign key constraints
    op.drop_table('scores')
    op.drop_table('gates')
    op.drop_table('signals')
    op.drop_table('trial_versions')
