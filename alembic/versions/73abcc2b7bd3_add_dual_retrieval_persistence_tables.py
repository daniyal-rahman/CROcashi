"""add_dual_retrieval_persistence_tables

Revision ID: 73abcc2b7bd3
Revises: e78153bd3545
Create Date: 2025-09-11 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '73abcc2b7bd3'
down_revision: Union[str, Sequence[str], None] = 'e78153bd3545'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add dual persistence tables for retrieval and processing."""
    
    # Create retrieval_documents table - stores ALL documents found during retrieval
    # This provides complete audit trail for human verification
    op.create_table('retrieval_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trial_id', sa.Integer(), nullable=False),
        sa.Column('pmid', sa.String(20), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('authors', postgresql.JSONB(), nullable=True),
        sa.Column('journal', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retrieval_score', sa.Float(), nullable=True),
        sa.Column('retrieval_tier', sa.String(10), nullable=True),
        sa.Column('query_tier', sa.String(10), nullable=True),  # A, B, C, D
        sa.Column('policy_engine_passed', sa.Boolean(), nullable=True),
        sa.Column('guardrails_passed', sa.Boolean(), nullable=True),
        sa.Column('retrieval_metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.CheckConstraint("retrieval_tier::text = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text])", name='ck_retrieval_documents_retrieval_tier')
    )
    
    # Create indexes for retrieval_documents
    op.create_index('ix_retrieval_documents_trial_id', 'retrieval_documents', ['trial_id'])
    op.create_index('ix_retrieval_documents_pmid', 'retrieval_documents', ['pmid'])
    op.create_index('ix_retrieval_documents_retrieval_tier', 'retrieval_documents', ['retrieval_tier'])
    op.create_index('ix_retrieval_documents_query_tier', 'retrieval_documents', ['query_tier'])
    op.create_index('ix_retrieval_documents_published_at', 'retrieval_documents', ['published_at'])
    op.create_index('ix_retrieval_documents_retrieval_score', 'retrieval_documents', ['retrieval_score'])
    
    # Create processed_documents table - stores only filtered, processed documents
    # This provides the pruned set for LLM processing
    op.create_table('processed_documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trial_id', sa.Integer(), nullable=False),
        sa.Column('retrieval_doc_id', sa.Integer(), nullable=True),  # Link back to retrieval_documents
        sa.Column('pmid', sa.String(20), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('abstract', sa.Text(), nullable=True),
        sa.Column('r_score', sa.Float(), nullable=True),
        sa.Column('s_score', sa.Float(), nullable=True),
        sa.Column('rs_tier', sa.String(10), nullable=True),
        sa.Column('entities', postgresql.JSONB(), nullable=True),
        sa.Column('processing_metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['retrieval_doc_id'], ['retrieval_documents.id'], ondelete='SET NULL'),
        sa.CheckConstraint("rs_tier::text = ANY (ARRAY['R0S0'::text, 'R0S1'::text, 'R1S0'::text, 'R1S1'::text, 'R2S0'::text, 'R2S1'::text, 'R0S2'::text, 'R1S2'::text, 'R2S2'::text, 'R3S0'::text, 'R3S1'::text, 'R3S2'::text, 'R0S3'::text, 'R1S3'::text, 'R2S3'::text, 'R3S3'::text])", name='ck_processed_documents_rs_tier')
    )
    
    # Create indexes for processed_documents
    op.create_index('ix_processed_documents_trial_id', 'processed_documents', ['trial_id'])
    op.create_index('ix_processed_documents_pmid', 'processed_documents', ['pmid'])
    op.create_index('ix_processed_documents_rs_tier', 'processed_documents', ['rs_tier'])
    op.create_index('ix_processed_documents_r_score', 'processed_documents', ['r_score'])
    op.create_index('ix_processed_documents_s_score', 'processed_documents', ['s_score'])
    op.create_index('ix_processed_documents_retrieval_doc_id', 'processed_documents', ['retrieval_doc_id'])
    
    # Create retrieval_sessions table - tracks retrieval runs for audit
    op.create_table('retrieval_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('trial_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(50), nullable=False),
        sa.Column('asset_aliases', postgresql.JSONB(), nullable=True),
        sa.Column('indication_terms', postgresql.JSONB(), nullable=True),
        sa.Column('query_metadata', postgresql.JSONB(), nullable=True),
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
    
    # Create indexes for retrieval_sessions
    op.create_index('ix_retrieval_sessions_trial_id', 'retrieval_sessions', ['trial_id'])
    op.create_index('ix_retrieval_sessions_session_id', 'retrieval_sessions', ['session_id'])
    op.create_index('ix_retrieval_sessions_status', 'retrieval_sessions', ['status'])
    op.create_index('ix_retrieval_sessions_created_at', 'retrieval_sessions', ['created_at'])
    
    # Add comment explaining the dual persistence strategy
    op.execute("COMMENT ON TABLE retrieval_documents IS 'Stores ALL documents found during retrieval for complete audit trail and human verification'")
    op.execute("COMMENT ON TABLE processed_documents IS 'Stores only filtered, processed documents ready for LLM processing'")
    op.execute("COMMENT ON TABLE retrieval_sessions IS 'Tracks retrieval runs for audit and debugging purposes'")


def downgrade() -> None:
    """Downgrade schema - Remove dual persistence tables."""
    op.drop_table('retrieval_sessions')
    op.drop_table('processed_documents')
    op.drop_table('retrieval_documents')