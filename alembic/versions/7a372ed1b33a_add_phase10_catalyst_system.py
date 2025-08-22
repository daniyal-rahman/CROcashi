"""add_phase10_catalyst_system

Revision ID: 7a372ed1b33a
Revises: 20250124_add_resolver_system_and_company_securities
Create Date: 2025-08-22 12:42:22.769140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7a372ed1b33a'
down_revision: Union[str, Sequence[str], None] = '20250124_add_resolver_system_and_company_securities'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Phase 10 catalyst system tables and views with idempotent operations."""
    
    # Check if tables already exist to make migration idempotent
    def table_exists(table_name: str) -> bool:
        connection = op.get_bind()
        result = connection.execute(
            sa.text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"),
            {"table_name": table_name}
        ).scalar()
        return result
    
    def view_exists(view_name: str) -> bool:
        connection = op.get_bind()
        result = connection.execute(
            sa.text("SELECT EXISTS (SELECT FROM information_schema.views WHERE table_name = :view_name)"),
            {"view_name": view_name}
        ).scalar()
        return result
    
    def index_exists(index_name: str) -> bool:
        connection = op.get_bind()
        result = connection.execute(
            sa.text("SELECT EXISTS (SELECT FROM pg_indexes WHERE indexname = :index_name)"),
            {"index_name": index_name}
        ).scalar()
        return result
    
    def function_exists(function_name: str) -> bool:
        connection = op.get_bind()
        result = connection.execute(
            sa.text("SELECT EXISTS (SELECT FROM pg_proc WHERE proname = :function_name)"),
            {"function_name": function_name}
        ).scalar()
        return result
    
    def trigger_exists(trigger_name: str) -> bool:
        connection = op.get_bind()
        result = connection.execute(
            sa.text("SELECT EXISTS (SELECT FROM pg_trigger WHERE tgname = :trigger_name)"),
            {"trigger_name": trigger_name}
        ).scalar()
        return result

    # Create sponsor_slip_stats table
    if not table_exists("sponsor_slip_stats"):
        op.create_table(
            'sponsor_slip_stats',
            sa.Column('company_id', sa.BigInteger(), nullable=False),
            sa.Column('mean_slip_days', sa.Integer(), nullable=False),
            sa.Column('p10_days', sa.Integer(), nullable=False),
            sa.Column('p90_days', sa.Integer(), nullable=False),
            sa.Column('n_events', sa.Integer(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('company_id')
        )
        
        # Create indexes for sponsor_slip_stats
        op.create_index('ix_sponsor_slip_stats_company_id', 'sponsor_slip_stats', ['company_id'])
        op.create_index('ix_sponsor_slip_stats_updated_at', 'sponsor_slip_stats', ['updated_at'])

    # Create study_card_rankings table
    if not table_exists("study_card_rankings"):
        op.create_table(
            'study_card_rankings',
            sa.Column('ranking_id', sa.BigInteger(), nullable=False),
            sa.Column('trial_id', sa.BigInteger(), nullable=False),
            sa.Column('evaluator_id', sa.String(length=100), nullable=False),
            sa.Column('score_1_10', sa.Integer(), nullable=False),
            sa.Column('confidence_level', sa.Integer(), nullable=True),
            sa.Column('reasoning_text', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('ranking_id'),
            sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
            sa.CheckConstraint("score_1_10 >= 1 AND score_1_10 <= 10", name='ck_study_card_rankings_score_range'),
            sa.CheckConstraint("confidence_level IS NULL OR (confidence_level >= 1 AND confidence_level <= 5)", name='ck_study_card_rankings_confidence_range'),
            sa.UniqueConstraint('trial_id', 'evaluator_id', name='uq_study_card_rankings_trial_evaluator')
        )
        
        # Create indexes for study_card_rankings
        op.create_index('ix_study_card_rankings_trial_id', 'study_card_rankings', ['trial_id'])
        op.create_index('ix_study_card_rankings_score', 'study_card_rankings', ['score_1_10'])
        op.create_index('ix_study_card_rankings_evaluator', 'study_card_rankings', ['evaluator_id'])
        op.create_index('ix_study_card_rankings_created_at', 'study_card_rankings', ['created_at'])

    # Create llm_resolution_scores table
    if not table_exists("llm_resolution_scores"):
        op.create_table(
            'llm_resolution_scores',
            sa.Column('resolution_id', sa.BigInteger(), nullable=False),
            sa.Column('trial_id', sa.BigInteger(), nullable=False),
            sa.Column('base_score_1_10', sa.Integer(), nullable=False),
            sa.Column('expanded_score_1_100', sa.Integer(), nullable=False),
            sa.Column('llm_provider', sa.String(length=50), nullable=False),
            sa.Column('llm_model', sa.String(length=100), nullable=True),
            sa.Column('prompt_version', sa.String(length=20), nullable=True),
            sa.Column('reasoning_text', sa.Text(), nullable=True),
            sa.Column('confidence_score', sa.Numeric(precision=3, scale=2), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('resolution_id'),
            sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
            sa.CheckConstraint("base_score_1_10 >= 1 AND base_score_1_10 <= 10", name='ck_llm_resolution_base_score_range'),
            sa.CheckConstraint("expanded_score_1_100 >= 1 AND expanded_score_1_100 <= 100", name='ck_llm_resolution_expanded_score_range'),
            sa.CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0.0 AND confidence_score <= 1.0)", name='ck_llm_resolution_confidence_range'),
            sa.UniqueConstraint('trial_id', 'base_score_1_10', 'llm_provider', name='uq_llm_resolution_trial_score_provider')
        )
        
        # Create indexes for llm_resolution_scores
        op.create_index('ix_llm_resolution_scores_trial_id', 'llm_resolution_scores', ['trial_id'])
        op.create_index('ix_llm_resolution_scores_base_score', 'llm_resolution_scores', ['base_score_1_10'])
        op.create_index('ix_llm_resolution_scores_expanded', 'llm_resolution_scores', ['expanded_score_1_100'])
        op.create_index('ix_llm_resolution_scores_provider', 'llm_resolution_scores', ['llm_provider'])

    # Create catalysts table
    if not table_exists("catalysts"):
        op.create_table(
            'catalysts',
            sa.Column('catalyst_id', sa.BigInteger(), nullable=False),
            sa.Column('trial_id', sa.BigInteger(), nullable=False),
            sa.Column('window_start', sa.Date(), nullable=False),
            sa.Column('window_end', sa.Date(), nullable=False),
            sa.Column('certainty', sa.Numeric(precision=3, scale=2), nullable=False),
            sa.Column('sources', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('catalyst_id'),
            sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
            sa.CheckConstraint("certainty >= 0.0 AND certainty <= 1.0", name='ck_catalysts_certainty_range'),
            sa.CheckConstraint("window_start <= window_end", name='ck_catalysts_window_order'),
            sa.UniqueConstraint('trial_id', name='uq_catalysts_trial_id')
        )
        
        # Create indexes for catalysts
        op.create_index('ix_catalysts_trial_id', 'catalysts', ['trial_id'])
        op.create_index('ix_catalysts_window', 'catalysts', ['window_start', 'window_end'])
        op.create_index('ix_catalysts_certainty', 'catalysts', ['certainty'])
        op.create_index('ix_catalysts_created_at', 'catalysts', ['created_at'])

    # Create backtesting framework tables (hooks only)
    if not table_exists("backtest_runs"):
        op.create_table(
            'backtest_runs',
            sa.Column('run_id', sa.BigInteger(), nullable=False),
            sa.Column('run_name', sa.String(length=200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('start_date', sa.Date(), nullable=False),
            sa.Column('end_date', sa.Date(), nullable=False),
            sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('run_id'),
            sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed')", name='ck_backtest_runs_status_valid'),
            sa.CheckConstraint("start_date <= end_date", name='ck_backtest_runs_date_order')
        )
        
        # Create indexes for backtest_runs
        op.create_index('ix_backtest_runs_status', 'backtest_runs', ['status'])
        op.create_index('ix_backtest_runs_dates', 'backtest_runs', ['start_date', 'end_date'])
        op.create_index('ix_backtest_runs_created_at', 'backtest_runs', ['created_at'])

    if not table_exists("backtest_snapshots"):
        op.create_table(
            'backtest_snapshots',
            sa.Column('snapshot_id', sa.BigInteger(), nullable=False),
            sa.Column('run_id', sa.BigInteger(), nullable=False),
            sa.Column('trial_id', sa.BigInteger(), nullable=False),
            sa.Column('snapshot_date', sa.Date(), nullable=False),
            sa.Column('study_card_rank', sa.Integer(), nullable=True),
            sa.Column('llm_resolution_score', sa.Integer(), nullable=True),
            sa.Column('p_fail', sa.Numeric(precision=5, scale=4), nullable=True),
            sa.Column('catalyst_window_start', sa.Date(), nullable=True),
            sa.Column('catalyst_window_end', sa.Date(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('snapshot_id'),
            sa.ForeignKeyConstraint(['run_id'], ['backtest_runs.run_id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
            sa.UniqueConstraint('run_id', 'trial_id', 'snapshot_date', name='uq_backtest_snapshots_run_trial_date')
        )
        
        # Create indexes for backtest_snapshots
        op.create_index('ix_backtest_snapshots_run_trial', 'backtest_snapshots', ['run_id', 'trial_id'])
        op.create_index('ix_backtest_snapshots_date', 'backtest_snapshots', ['snapshot_date'])
        op.create_index('ix_backtest_snapshots_trial_id', 'backtest_snapshots', ['trial_id'])

    if not table_exists("backtest_results"):
        op.create_table(
            'backtest_results',
            sa.Column('result_id', sa.BigInteger(), nullable=False),
            sa.Column('run_id', sa.BigInteger(), nullable=False),
            sa.Column('k_value', sa.Integer(), nullable=False),
            sa.Column('precision_at_k', sa.Numeric(precision=5, scale=4), nullable=True),
            sa.Column('recall_at_k', sa.Numeric(precision=5, scale=4), nullable=True),
            sa.Column('f1_at_k', sa.Numeric(precision=5, scale=4), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('result_id'),
            sa.ForeignKeyConstraint(['run_id'], ['backtest_runs.run_id'], ondelete='CASCADE'),
            sa.UniqueConstraint('run_id', 'k_value', name='uq_backtest_results_run_k')
        )
        
        # Create indexes for backtest_results
        op.create_index('ix_backtest_results_run_id', 'backtest_results', ['run_id'])
        op.create_index('ix_backtest_results_k_value', 'backtest_results', ['k_value'])

    # Create function to update updated_at timestamp
    if not function_exists("update_updated_at_column"):
        op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)

    # Create triggers for updated_at
    if not trigger_exists("update_study_card_rankings_updated_at"):
        op.execute("""
        CREATE TRIGGER update_study_card_rankings_updated_at
            BEFORE UPDATE ON study_card_rankings
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)

    if not trigger_exists("update_catalysts_updated_at"):
        op.execute("""
        CREATE TRIGGER update_catalysts_updated_at
            BEFORE UPDATE ON catalysts
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)

    # Create views for dashboard and ranking
    if not view_exists("v_latest_scores"):
        op.execute("""
        CREATE OR REPLACE VIEW v_latest_scores AS
        SELECT DISTINCT ON (trial_id)
            trial_id, run_id, p_fail, logit_post, sum_log_lr
        FROM scores
        ORDER BY trial_id, run_id DESC;
        """)

    if not view_exists("v_study_card_rankings_agg"):
        op.execute("""
        CREATE OR REPLACE VIEW v_study_card_rankings_agg AS
        SELECT 
            trial_id,
            COUNT(*) as evaluator_count,
            AVG(score_1_10) as mean_score,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY score_1_10) as median_score,
            MIN(score_1_10) as min_score,
            MAX(score_1_10) as max_score,
            STDDEV(score_1_10) as score_stddev,
            MAX(updated_at) as last_updated
        FROM study_card_rankings
        GROUP BY trial_id;
        """)

    if not view_exists("v_llm_resolution_agg"):
        op.execute("""
        CREATE OR REPLACE VIEW v_llm_resolution_agg AS
        SELECT 
            trial_id,
            base_score_1_10,
            AVG(expanded_score_1_100) as mean_expanded_score,
            MAX(expanded_score_1_100) as max_expanded_score,
            MIN(expanded_score_1_100) as min_expanded_score,
            COUNT(*) as resolution_count,
            MAX(created_at) as last_resolved
        FROM llm_resolution_scores
        GROUP BY trial_id, base_score_1_10;
        """)

    if not view_exists("v_trial_catalysts"):
        op.execute("""
        CREATE OR REPLACE VIEW v_trial_catalysts AS
        SELECT 
            t.trial_id, 
            t.nct_id, 
            t.phase, 
            t.is_pivotal,
            t.sponsor_company_id,
            t.est_primary_completion_date,
            c.window_start, 
            c.window_end, 
            c.certainty,
            COALESCE(s.p_fail, 0.0) as p_fail,
            COALESCE(scr.mean_score, 0.0) as study_card_score,
            COALESCE(lra.mean_expanded_score, 0.0) as llm_resolution_score,
            array_remove(array[
                CASE WHEN g1.fired_bool THEN 'G1' END,
                CASE WHEN g2.fired_bool THEN 'G2' END,
                CASE WHEN g3.fired_bool THEN 'G3' END,
                CASE WHEN g4.fired_bool THEN 'G4' END
            ], NULL) AS gates
        FROM trials t
        LEFT JOIN v_latest_scores s USING (trial_id)
        LEFT JOIN catalysts c USING (trial_id)
        LEFT JOIN v_study_card_rankings_agg scr USING (trial_id)
        LEFT JOIN v_llm_resolution_agg lra ON (lra.trial_id = t.trial_id AND lra.base_score_1_10 = scr.mean_score::INTEGER)
        LEFT JOIN LATERAL (
            SELECT fired_bool FROM gates WHERE trial_id=t.trial_id AND "G_id"='G1'
        ) g1 ON TRUE
        LEFT JOIN LATERAL (
            SELECT fired_bool FROM gates WHERE trial_id=t.trial_id AND "G_id"='G2'
        ) g2 ON TRUE
        LEFT JOIN LATERAL (
            SELECT fired_bool FROM gates WHERE trial_id=t.trial_id AND "G_id"='G3'
        ) g3 ON TRUE
        LEFT JOIN LATERAL (
            SELECT fired_bool FROM gates WHERE trial_id=t.trial_id AND "G_id"='G4'
        ) g4 ON TRUE
        WHERE t.is_pivotal IS TRUE;
        """)

    # Insert default sponsor slip stats (placeholder)
    op.execute("""
    INSERT INTO sponsor_slip_stats (company_id, mean_slip_days, p10_days, p90_days, n_events)
    VALUES 
        (0, 15, -5, 35, 100),  -- Default fallback
        (1, 20, 0, 45, 50),    -- Example company
        (2, 10, -10, 30, 75)   -- Example company
    ON CONFLICT (company_id) DO NOTHING;
    """)


def downgrade() -> None:
    """Remove Phase 10 catalyst system tables and views."""
    
    # Drop views first
    op.execute("DROP VIEW IF EXISTS v_trial_catalysts")
    op.execute("DROP VIEW IF EXISTS v_llm_resolution_agg")
    op.execute("DROP VIEW IF EXISTS v_study_card_rankings_agg")
    op.execute("DROP VIEW IF EXISTS v_latest_scores")
    
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_catalysts_updated_at ON catalysts")
    op.execute("DROP TRIGGER IF EXISTS update_study_card_rankings_updated_at ON study_card_rankings")
    
    # Drop function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    
    # Drop tables
    op.drop_table('backtest_results')
    op.drop_table('backtest_snapshots')
    op.drop_table('backtest_runs')
    op.drop_table('catalysts')
    op.drop_table('llm_resolution_scores')
    op.drop_table('study_card_rankings')
    op.drop_table('sponsor_slip_stats')
