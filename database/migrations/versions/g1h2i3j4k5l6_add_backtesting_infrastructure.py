"""add backtesting infrastructure tables

Revision ID: g1h2i3j4k5l6
Revises: 8c7d7a4ddcf8
Create Date: 2025-12-03 10:00:00.000000

This migration adds:
- company_tickers: Temporal ticker mapping with SEC CIK
- stock_prices: Historical daily stock prices
- historical_catalysts: Core backtesting table with outcomes
- catalyst_flag_cache: Pre-computed point-in-time flag values
- fda_applications: FDA drug applications (NDA, BLA, ANDA)
- fda_submissions: FDA submission events and decisions

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, None] = '8c7d7a4ddcf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # Table: company_tickers
    # =========================================================================
    op.create_table(
        'company_tickers',
        sa.Column('ticker_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ticker', sa.String(20), nullable=False),
        sa.Column('cik', sa.String(20), nullable=True),
        sa.Column('exchange', sa.String(50), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('is_primary', sa.Boolean(), default=True),
        sa.Column('data_sources', postgresql.JSONB(), nullable=True),
        # Base model columns
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text(), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        # Constraints
        sa.UniqueConstraint('company_id', 'ticker', 'valid_from', name='uq_company_ticker_period'),
    )
    op.create_index('ix_company_tickers_ticker_id', 'company_tickers', ['ticker_id'])
    op.create_index('ix_company_tickers_company_id', 'company_tickers', ['company_id'])
    op.create_index('ix_company_tickers_ticker', 'company_tickers', ['ticker'])
    op.create_index('ix_company_tickers_cik', 'company_tickers', ['cik'])
    op.create_index('ix_company_tickers_exchange', 'company_tickers', ['exchange'])
    op.create_index('ix_company_tickers_valid_from', 'company_tickers', ['valid_from'])
    op.create_index('ix_company_tickers_valid_until', 'company_tickers', ['valid_until'])
    op.create_index('ix_company_tickers_is_primary', 'company_tickers', ['is_primary'])
    op.create_index('ix_company_tickers_deleted_at', 'company_tickers', ['deleted_at'])
    # Partial index for active tickers
    op.execute("""
        CREATE INDEX ix_company_tickers_active
        ON company_tickers (company_id, is_primary)
        WHERE valid_until IS NULL AND deleted_at IS NULL
    """)

    # =========================================================================
    # Table: stock_prices
    # =========================================================================
    op.create_table(
        'stock_prices',
        sa.Column('price_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('price_date', sa.Date(), nullable=False),
        sa.Column('open_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('high_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('low_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('close_price', sa.Numeric(12, 4), nullable=False),
        sa.Column('adjusted_close', sa.Numeric(12, 4), nullable=True),
        sa.Column('volume', sa.BigInteger(), nullable=True),
        sa.Column('pct_change_1d', sa.Numeric(8, 4), nullable=True),
        sa.Column('high_52w', sa.Numeric(12, 4), nullable=True),
        sa.Column('low_52w', sa.Numeric(12, 4), nullable=True),
        sa.Column('data_sources', postgresql.JSONB(), nullable=True),
        # Base model columns
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text(), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        # Constraints
        sa.UniqueConstraint('company_id', 'price_date', name='uq_company_price_date'),
    )
    op.create_index('ix_stock_prices_price_id', 'stock_prices', ['price_id'])
    op.create_index('ix_stock_prices_company_id', 'stock_prices', ['company_id'])
    op.create_index('ix_stock_prices_price_date', 'stock_prices', ['price_date'])
    op.create_index('ix_stock_prices_company_date', 'stock_prices', ['company_id', 'price_date'])
    op.create_index('ix_stock_prices_deleted_at', 'stock_prices', ['deleted_at'])

    # =========================================================================
    # Table: fda_applications
    # =========================================================================
    op.create_table(
        'fda_applications',
        sa.Column('application_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('application_number', sa.String(50), nullable=False, unique=True),
        sa.Column('application_type', sa.String(20), nullable=False),
        sa.Column('drug_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('sponsor_name', sa.String(500), nullable=True),
        sa.Column('brand_name', sa.String(500), nullable=True),
        sa.Column('generic_name', sa.String(500), nullable=True),
        sa.Column('current_status', sa.String(100), nullable=True),
        sa.Column('submission_date', sa.Date(), nullable=True),
        sa.Column('approval_date', sa.Date(), nullable=True),
        sa.Column('data_sources', postgresql.JSONB(), nullable=True),
        # Base model columns
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text(), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(['drug_id'], ['drugs.drug_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='SET NULL'),
        # Check constraints
        sa.CheckConstraint(
            "application_type IN ('NDA', 'BLA', 'ANDA', 'IND')",
            name='check_fda_application_type'
        ),
    )
    op.create_index('ix_fda_applications_application_id', 'fda_applications', ['application_id'])
    op.create_index('ix_fda_applications_application_number', 'fda_applications', ['application_number'])
    op.create_index('ix_fda_applications_application_type', 'fda_applications', ['application_type'])
    op.create_index('ix_fda_applications_drug_id', 'fda_applications', ['drug_id'])
    op.create_index('ix_fda_applications_company_id', 'fda_applications', ['company_id'])
    op.create_index('ix_fda_applications_current_status', 'fda_applications', ['current_status'])
    op.create_index('ix_fda_applications_submission_date', 'fda_applications', ['submission_date'])
    op.create_index('ix_fda_applications_approval_date', 'fda_applications', ['approval_date'])
    op.create_index('ix_fda_applications_sponsor', 'fda_applications', ['sponsor_name'])
    op.create_index('ix_fda_applications_deleted_at', 'fda_applications', ['deleted_at'])

    # =========================================================================
    # Table: fda_submissions
    # =========================================================================
    op.create_table(
        'fda_submissions',
        sa.Column('submission_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('application_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('submission_type', sa.String(50), nullable=False),
        sa.Column('submission_number', sa.Integer(), nullable=True),
        sa.Column('submission_date', sa.Date(), nullable=True),
        sa.Column('action_date', sa.Date(), nullable=True),
        sa.Column('action_type', sa.String(50), nullable=True),
        sa.Column('review_priority', sa.String(50), nullable=True),
        sa.Column('orphan_designation', sa.Boolean(), default=False),
        sa.Column('data_sources', postgresql.JSONB(), nullable=True),
        # Base model columns
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text(), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(['application_id'], ['fda_applications.application_id'], ondelete='CASCADE'),
        # Check constraints
        sa.CheckConstraint(
            "action_type IN ('AP', 'CRL', 'TA', 'WD', 'RL') OR action_type IS NULL",
            name='check_fda_submission_action_type'
        ),
        sa.CheckConstraint(
            "submission_type IN ('ORIG', 'SUPPL', 'EFFCT', 'MANUF', 'REMS') OR submission_type IS NULL",
            name='check_fda_submission_type'
        ),
    )
    op.create_index('ix_fda_submissions_submission_id', 'fda_submissions', ['submission_id'])
    op.create_index('ix_fda_submissions_application_id', 'fda_submissions', ['application_id'])
    op.create_index('ix_fda_submissions_submission_type', 'fda_submissions', ['submission_type'])
    op.create_index('ix_fda_submissions_submission_date', 'fda_submissions', ['submission_date'])
    op.create_index('ix_fda_submissions_action_date', 'fda_submissions', ['action_date'])
    op.create_index('ix_fda_submissions_action_type', 'fda_submissions', ['action_type'])
    op.create_index('ix_fda_submissions_action', 'fda_submissions', ['action_type', 'action_date'])
    op.create_index('ix_fda_submissions_deleted_at', 'fda_submissions', ['deleted_at'])

    # =========================================================================
    # Table: historical_catalysts
    # =========================================================================
    op.create_table(
        'historical_catalysts',
        sa.Column('catalyst_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('drug_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('trial_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('disease_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('catalyst_type', sa.String(100), nullable=False),
        sa.Column('catalyst_date', sa.Date(), nullable=False),
        sa.Column('announced_date', sa.Date(), nullable=True),
        sa.Column('outcome', sa.String(50), nullable=False),
        sa.Column('outcome_severity', sa.String(50), nullable=True),
        sa.Column('stock_reaction_1d', sa.Numeric(8, 4), nullable=True),
        sa.Column('stock_reaction_5d', sa.Numeric(8, 4), nullable=True),
        sa.Column('phase', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_type', sa.String(100), nullable=True),
        sa.Column('source_url', sa.String(1000), nullable=True),
        sa.Column('data_sources', postgresql.JSONB(), nullable=True),
        sa.Column('manually_verified', sa.Boolean(), default=False),
        # Base model columns
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text(), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['drug_id'], ['drugs.drug_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['trial_id'], ['clinical_trials.trial_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['disease_id'], ['diseases.disease_id'], ondelete='SET NULL'),
        # Constraints
        sa.CheckConstraint(
            "outcome IN ('positive', 'negative', 'mixed', 'neutral')",
            name='check_catalyst_outcome'
        ),
        sa.CheckConstraint(
            "outcome_severity IN ('mild', 'moderate', 'severe', 'catastrophic') OR outcome_severity IS NULL",
            name='check_outcome_severity'
        ),
        sa.UniqueConstraint('company_id', 'drug_id', 'catalyst_type', 'catalyst_date', name='uq_catalyst_event'),
    )
    op.create_index('ix_historical_catalysts_catalyst_id', 'historical_catalysts', ['catalyst_id'])
    op.create_index('ix_historical_catalysts_company_id', 'historical_catalysts', ['company_id'])
    op.create_index('ix_historical_catalysts_drug_id', 'historical_catalysts', ['drug_id'])
    op.create_index('ix_historical_catalysts_trial_id', 'historical_catalysts', ['trial_id'])
    op.create_index('ix_historical_catalysts_disease_id', 'historical_catalysts', ['disease_id'])
    op.create_index('ix_historical_catalysts_catalyst_type', 'historical_catalysts', ['catalyst_type'])
    op.create_index('ix_historical_catalysts_catalyst_date', 'historical_catalysts', ['catalyst_date'])
    op.create_index('ix_historical_catalysts_outcome', 'historical_catalysts', ['outcome'])
    op.create_index('ix_historical_catalysts_manually_verified', 'historical_catalysts', ['manually_verified'])
    op.create_index('ix_catalysts_date_type', 'historical_catalysts', ['catalyst_date', 'catalyst_type'])
    op.create_index('ix_catalysts_outcome', 'historical_catalysts', ['outcome', 'catalyst_date'])
    op.create_index('ix_historical_catalysts_deleted_at', 'historical_catalysts', ['deleted_at'])

    # =========================================================================
    # Table: catalyst_flag_cache
    # =========================================================================
    op.create_table(
        'catalyst_flag_cache',
        sa.Column('cache_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('catalyst_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('computed_at_date', sa.Date(), nullable=False),
        # Individual flags
        sa.Column('graveyard_indication', sa.Boolean(), default=False),
        sa.Column('graveyard_indication_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('high_company_termination_rate', sa.Boolean(), default=False),
        sa.Column('company_termination_rate', sa.Numeric(5, 4), nullable=True),
        sa.Column('single_asset_company', sa.Boolean(), default=False),
        sa.Column('pipeline_count', sa.Integer(), nullable=True),
        sa.Column('down_80_pct', sa.Boolean(), default=False),
        sa.Column('pct_from_3y_high', sa.Numeric(8, 4), nullable=True),
        sa.Column('prior_drug_failure', sa.Boolean(), default=False),
        sa.Column('prior_failure_count', sa.Integer(), nullable=True),
        # Composite
        sa.Column('any_flag_triggered', sa.Boolean(), default=False),
        sa.Column('flag_count', sa.Integer(), default=0),
        sa.Column('calculation_version', sa.String(50), nullable=True),
        # Base model columns
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text(), nullable=True),
        # Foreign keys
        sa.ForeignKeyConstraint(['catalyst_id'], ['historical_catalysts.catalyst_id'], ondelete='CASCADE'),
        # Constraints
        sa.UniqueConstraint('catalyst_id', 'computed_at_date', 'calculation_version', name='uq_catalyst_flag_cache'),
    )
    op.create_index('ix_catalyst_flag_cache_cache_id', 'catalyst_flag_cache', ['cache_id'])
    op.create_index('ix_catalyst_flag_cache_catalyst_id', 'catalyst_flag_cache', ['catalyst_id'])
    op.create_index('ix_catalyst_flag_cache_computed_at_date', 'catalyst_flag_cache', ['computed_at_date'])
    op.create_index('ix_catalyst_flag_cache_graveyard_indication', 'catalyst_flag_cache', ['graveyard_indication'])
    op.create_index('ix_catalyst_flag_cache_high_company_termination_rate', 'catalyst_flag_cache', ['high_company_termination_rate'])
    op.create_index('ix_catalyst_flag_cache_single_asset_company', 'catalyst_flag_cache', ['single_asset_company'])
    op.create_index('ix_catalyst_flag_cache_down_80_pct', 'catalyst_flag_cache', ['down_80_pct'])
    op.create_index('ix_catalyst_flag_cache_prior_drug_failure', 'catalyst_flag_cache', ['prior_drug_failure'])
    op.create_index('ix_catalyst_flag_cache_any_flag_triggered', 'catalyst_flag_cache', ['any_flag_triggered'])
    op.create_index('ix_flag_cache_any_triggered', 'catalyst_flag_cache', ['any_flag_triggered', 'computed_at_date'])
    op.create_index('ix_catalyst_flag_cache_deleted_at', 'catalyst_flag_cache', ['deleted_at'])


def downgrade() -> None:
    # Drop tables in reverse order of creation (respecting foreign key dependencies)
    op.drop_table('catalyst_flag_cache')
    op.drop_table('historical_catalysts')
    op.drop_table('fda_submissions')
    op.drop_table('fda_applications')
    op.drop_table('stock_prices')
    op.drop_table('company_tickers')
