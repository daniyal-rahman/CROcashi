"""add_trial_association_to_documents

Revision ID: 46e2cf011429
Revises: 949dce52fffb
Create Date: 2025-09-20 10:06:31.237332

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '46e2cf011429'
down_revision: Union[str, Sequence[str], None] = '949dce52fffb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add trial association fields to documents table."""
    
    # Add trial association fields to documents table
    op.add_column('documents', sa.Column('trial_id', sa.Integer(), nullable=True))
    op.add_column('documents', sa.Column('processing_status', sa.String(20), nullable=False, server_default='discovered'))
    op.add_column('documents', sa.Column('processing_priority', sa.String(10), nullable=True))
    op.add_column('documents', sa.Column('retrieval_tier', sa.String(10), nullable=True))
    op.add_column('documents', sa.Column('link_confidence', sa.Numeric(3,2), nullable=True))
    op.add_column('documents', sa.Column('scored_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('selected_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('study_card_generated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documents', sa.Column('processing_notes', sa.Text(), nullable=True))
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_documents_trial_id_trials',
        'documents', 'trials',
        ['trial_id'], ['trial_id'],
        ondelete='CASCADE'
    )
    
    # Add indexes for performance
    op.create_index('ix_documents_trial_id', 'documents', ['trial_id'])
    op.create_index('ix_documents_processing_status', 'documents', ['processing_status'])
    op.create_index('ix_documents_processing_priority', 'documents', ['processing_priority'])
    op.create_index('ix_documents_retrieval_tier', 'documents', ['retrieval_tier'])
    
    # Add check constraints
    op.create_check_constraint(
        'ck_documents_processing_status',
        'documents',
        "processing_status::text = ANY (ARRAY['discovered','scored','selected','processed','study_card_generated']::text[])"
    )
    
    op.create_check_constraint(
        'ck_documents_processing_priority',
        'documents',
        "processing_priority::text = ANY (ARRAY['HIGH','MEDIUM','LOW','FALLBACK']::text[])"
    )
    
    op.create_check_constraint(
        'ck_documents_retrieval_tier',
        'documents',
        "retrieval_tier::text = ANY (ARRAY['A','B','C','D']::text[])"
    )
    
    op.create_check_constraint(
        'ck_documents_link_confidence_range',
        'documents',
        'link_confidence IS NULL OR (link_confidence >= 0 AND link_confidence <= 1)'
    )


def downgrade() -> None:
    """Remove trial association fields from documents table."""
    
    # Drop check constraints
    op.drop_constraint('ck_documents_link_confidence_range', 'documents')
    op.drop_constraint('ck_documents_retrieval_tier', 'documents')
    op.drop_constraint('ck_documents_processing_priority', 'documents')
    op.drop_constraint('ck_documents_processing_status', 'documents')
    
    # Drop indexes
    op.drop_index('ix_documents_retrieval_tier', 'documents')
    op.drop_index('ix_documents_processing_priority', 'documents')
    op.drop_index('ix_documents_processing_status', 'documents')
    op.drop_index('ix_documents_trial_id', 'documents')
    
    # Drop foreign key constraint
    op.drop_constraint('fk_documents_trial_id_trials', 'documents')
    
    # Drop columns
    op.drop_column('documents', 'processing_notes')
    op.drop_column('documents', 'study_card_generated_at')
    op.drop_column('documents', 'processed_at')
    op.drop_column('documents', 'selected_at')
    op.drop_column('documents', 'scored_at')
    op.drop_column('documents', 'link_confidence')
    op.drop_column('documents', 'retrieval_tier')
    op.drop_column('documents', 'processing_priority')
    op.drop_column('documents', 'processing_status')
    op.drop_column('documents', 'trial_id')
