"""remove_dual_persistence_tables_and_add_processing_stage

Revision ID: 3651d4b376ac
Revises: 47c6ec20aeb8
Create Date: 2025-09-12 23:34:33.303916

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3651d4b376ac'
down_revision: Union[str, Sequence[str], None] = '47c6ec20aeb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Remove dual persistence tables and add processing_stage to documents."""
    
    # Add processing_stage field to documents table
    op.add_column('documents', sa.Column('processing_stage', sa.String(20), nullable=False, server_default='raw'))
    
    # Create index for processing_stage
    op.create_index('ix_documents_processing_stage', 'documents', ['processing_stage'])
    
    # Add comment explaining the processing_stage field
    op.execute("COMMENT ON COLUMN documents.processing_stage IS 'Processing stage: raw (found by queries), processed (passed filtering/scoring)'")
    
    # Drop dual persistence tables in dependency order
    # First drop foreign key constraints
    op.drop_constraint('fk_retrieval_documents_session_id', 'retrieval_documents', type_='foreignkey')
    
    # Drop indexes
    op.drop_index('ix_processed_documents_retrieval_doc_id', 'processed_documents')
    op.drop_index('ix_processed_documents_s_score', 'processed_documents')
    op.drop_index('ix_processed_documents_r_score', 'processed_documents')
    op.drop_index('ix_processed_documents_rs_tier', 'processed_documents')
    op.drop_index('ix_processed_documents_pmid', 'processed_documents')
    op.drop_index('ix_processed_documents_trial_id', 'processed_documents')
    
    op.drop_index('ix_retrieval_documents_retrieval_score', 'retrieval_documents')
    op.drop_index('ix_retrieval_documents_published_at', 'retrieval_documents')
    op.drop_index('ix_retrieval_documents_query_tier', 'retrieval_documents')
    op.drop_index('ix_retrieval_documents_retrieval_tier', 'retrieval_documents')
    op.drop_index('ix_retrieval_documents_pmid', 'retrieval_documents')
    op.drop_index('ix_retrieval_documents_trial_id', 'retrieval_documents')
    op.drop_index('ix_retrieval_documents_session_id', 'retrieval_documents')
    
    op.drop_index('ix_retrieval_sessions_created_at', 'retrieval_sessions')
    op.drop_index('ix_retrieval_sessions_status', 'retrieval_sessions')
    op.drop_index('ix_retrieval_sessions_session_id', 'retrieval_sessions')
    op.drop_index('ix_retrieval_sessions_trial_id', 'retrieval_sessions')
    
    # Drop tables
    op.drop_table('processed_documents')
    op.drop_table('retrieval_documents')
    op.drop_table('retrieval_sessions')


def downgrade() -> None:
    """Downgrade schema - Recreate dual persistence tables and remove processing_stage."""
    
    # Recreate dual persistence tables (simplified version)
    op.create_table('retrieval_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trial_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(50), nullable=False),
        sa.Column('asset_aliases', sa.JSON(), nullable=True),
        sa.Column('indication_terms', sa.JSON(), nullable=True),
        sa.Column('query_metadata', sa.JSON(), nullable=True),
        sa.Column('total_documents_found', sa.Integer(), nullable=True),
        sa.Column('documents_after_policy_engine', sa.Integer(), nullable=True),
        sa.Column('documents_after_guardrails', sa.Integer(), nullable=True),
        sa.Column('documents_after_processing', sa.Integer(), nullable=True),
        sa.Column('execution_time_seconds', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.CheckConstraint("status::text = ANY (ARRAY['running'::text, 'completed'::text, 'failed'::text])", name='ck_retrieval_sessions_status')
    )
    
    op.create_table('retrieval_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trial_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('pmid', sa.String(20), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('authors', sa.JSON(), nullable=True),
        sa.Column('journal', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retrieval_score', sa.Float(), nullable=True),
        sa.Column('retrieval_tier', sa.String(10), nullable=True),
        sa.Column('query_tier', sa.String(10), nullable=True),
        sa.Column('policy_engine_passed', sa.Boolean(), nullable=True),
        sa.Column('guardrails_passed', sa.Boolean(), nullable=True),
        sa.Column('retrieval_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['retrieval_sessions.id'], ondelete='SET NULL'),
        sa.CheckConstraint("retrieval_tier::text = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text])", name='ck_retrieval_documents_retrieval_tier')
    )
    
    op.create_table('processed_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trial_id', sa.Integer(), nullable=False),
        sa.Column('retrieval_doc_id', sa.Integer(), nullable=True),
        sa.Column('pmid', sa.String(20), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('r_score', sa.Float(), nullable=True),
        sa.Column('s_score', sa.Float(), nullable=True),
        sa.Column('rs_tier', sa.String(10), nullable=True),
        sa.Column('entities', sa.JSON(), nullable=True),
        sa.Column('processing_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['retrieval_doc_id'], ['retrieval_documents.id'], ondelete='SET NULL'),
        sa.CheckConstraint("rs_tier::text = ANY (ARRAY['R0S0'::text, 'R0S1'::text, 'R1S0'::text, 'R1S1'::text, 'R2S0'::text, 'R2S1'::text, 'R0S2'::text, 'R1S2'::text, 'R2S2'::text, 'R3S0'::text, 'R3S1'::text, 'R3S2'::text, 'R0S3'::text, 'R1S3'::text, 'R2S3'::text, 'R3S3'::text])", name='ck_processed_documents_rs_tier')
    )
    
    # Recreate indexes
    op.create_index('ix_retrieval_sessions_trial_id', 'retrieval_sessions', ['trial_id'])
    op.create_index('ix_retrieval_sessions_session_id', 'retrieval_sessions', ['session_id'])
    op.create_index('ix_retrieval_sessions_status', 'retrieval_sessions', ['status'])
    op.create_index('ix_retrieval_sessions_created_at', 'retrieval_sessions', ['created_at'])
    
    op.create_index('ix_retrieval_documents_trial_id', 'retrieval_documents', ['trial_id'])
    op.create_index('ix_retrieval_documents_pmid', 'retrieval_documents', ['pmid'])
    op.create_index('ix_retrieval_documents_retrieval_tier', 'retrieval_documents', ['retrieval_tier'])
    op.create_index('ix_retrieval_documents_query_tier', 'retrieval_documents', ['query_tier'])
    op.create_index('ix_retrieval_documents_published_at', 'retrieval_documents', ['published_at'])
    op.create_index('ix_retrieval_documents_retrieval_score', 'retrieval_documents', ['retrieval_score'])
    op.create_index('ix_retrieval_documents_session_id', 'retrieval_documents', ['session_id'])
    
    op.create_index('ix_processed_documents_trial_id', 'processed_documents', ['trial_id'])
    op.create_index('ix_processed_documents_pmid', 'processed_documents', ['pmid'])
    op.create_index('ix_processed_documents_rs_tier', 'processed_documents', ['rs_tier'])
    op.create_index('ix_processed_documents_r_score', 'processed_documents', ['r_score'])
    op.create_index('ix_processed_documents_s_score', 'processed_documents', ['s_score'])
    op.create_index('ix_processed_documents_retrieval_doc_id', 'processed_documents', ['retrieval_doc_id'])
    
    # Remove processing_stage field from documents
    op.drop_index('ix_documents_processing_stage', 'documents')
    op.drop_column('documents', 'processing_stage')
