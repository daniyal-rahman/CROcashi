"""Add p_value generated column and improve staging_errors table

This migration adds:
1. p_value generated column for faster lookups
2. Improved staging_errors table structure
3. Better indexes for performance

Revision ID: 20250123_add_p_value_column
Revises: 20250122_add_storage_refcounting
Create Date: 2025-01-23 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250123_add_p_value_column'
down_revision = '20250122_add_storage_refcounting'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add p_value generated column for faster lookups
    op.execute("""
        ALTER TABLE studies 
        ADD COLUMN IF NOT EXISTS p_value numeric 
        GENERATED ALWAYS AS (
            (extracted_jsonb #>> '{results,primary,0,p_value}')::numeric
        ) STORED;
    """)
    
    # Create index on p_value for hot lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_studies_p_value 
        ON studies(p_value) 
        WHERE p_value IS NOT NULL;
    """)
    
    # Improve staging_errors table structure
    # Drop existing table if it exists (from previous migration)
    op.execute("DROP TABLE IF EXISTS staging_errors CASCADE;")
    
    # Create improved staging_errors table
    op.create_table(
        'staging_errors',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('trial_id', sa.BigInteger(), nullable=True),
        sa.Column('study_id', sa.BigInteger(), nullable=True),
        sa.Column('error_type', sa.Text(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('extracted_jsonb', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['study_id'], ['studies.study_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
    )
    
    # Create indexes on staging_errors for performance
    op.create_index('ix_staging_errors_created_at', 'staging_errors', ['created_at'])
    op.create_index('ix_staging_errors_trial_id', 'staging_errors', ['trial_id'])
    op.create_index('ix_staging_errors_error_type', 'staging_errors', ['error_type'])
    
    # Add comments for documentation
    op.execute("""
        COMMENT ON TABLE staging_errors IS 'Error sink for failed validations and processing errors';
        COMMENT ON COLUMN staging_errors.id IS 'Primary key for error tracking';
        COMMENT ON COLUMN staging_errors.trial_id IS 'Associated trial if known';
        COMMENT ON COLUMN staging_errors.study_id IS 'Associated study if known';
        COMMENT ON COLUMN staging_errors.error_type IS 'Category of error (validation, processing, etc.)';
        COMMENT ON COLUMN staging_errors.error_message IS 'Detailed error description';
        COMMENT ON COLUMN staging_errors.extracted_jsonb IS 'JSON data that caused the error';
        COMMENT ON COLUMN staging_errors.created_at IS 'When the error occurred';
    """)


def downgrade() -> None:
    # Drop p_value column and index
    op.execute("DROP INDEX IF EXISTS ix_studies_p_value;")
    op.execute("ALTER TABLE studies DROP COLUMN IF EXISTS p_value;")
    
    # Drop staging_errors table and indexes
    op.drop_index('ix_staging_errors_error_type', table_name='staging_errors')
    op.drop_index('ix_staging_errors_trial_id', table_name='staging_errors')
    op.drop_index('ix_staging_errors_created_at', table_name='staging_errors')
    op.drop_table('staging_errors')
