"""Add Checkpoint 2 & 4 fields to documents and document_utilities tables

Revision ID: add_checkpoint2_4_fields
Revises: ff5fabb58e9c
Create Date: 2025-08-28 14:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_checkpoint2_4_fields'
down_revision = 'ff5fabb58e9c'
branch_labels = None
depends_on = None


def upgrade():
    """Add Checkpoint 2 & 4 fields to documents and document_utilities tables."""
    
    # Add columns to documents table
    op.add_column('documents', sa.Column('abstract_text', sa.Text(), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('abstract_storage_uri', sa.Text(), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('abstract_fetched_at', sa.DateTime(timezone=True), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('pub_types', postgresql.ARRAY(sa.Text()), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('article_type', sa.Text(), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('journal', sa.Text(), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('pub_year', sa.Integer(), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('is_open_access', sa.Boolean(), nullable=True, server_default='false'), if_not_exists=True)
    
    # Add Checkpoint 4 full text fields
    op.add_column('documents', sa.Column('fulltext_text', sa.Text(), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('fulltext_storage_uri', sa.Text(), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('fulltext_fetched_at', sa.DateTime(timezone=True), nullable=True), if_not_exists=True)
    op.add_column('documents', sa.Column('ttl_expires_at', sa.Date(), nullable=True), if_not_exists=True)
    
    # Add columns to document_utilities table
    op.add_column('document_utilities', sa.Column('stage', sa.SmallInteger(), nullable=False, server_default='0'), if_not_exists=True)
    op.add_column('document_utilities', sa.Column('selected', sa.Boolean(), nullable=True, server_default='false'), if_not_exists=True)
    op.add_column('document_utilities', sa.Column('dropped_reason', sa.Text(), nullable=True), if_not_exists=True)
    op.add_column('document_utilities', sa.Column('abstract_fetched_at', sa.DateTime(timezone=True), nullable=True), if_not_exists=True)
    op.add_column('document_utilities', sa.Column('needs_fulltext', sa.Boolean(), nullable=False, server_default='false'), if_not_exists=True)
    op.add_column('document_utilities', sa.Column('fulltext_requested_at', sa.DateTime(timezone=True), nullable=True), if_not_exists=True)
    op.add_column('document_utilities', sa.Column('uncertainty', sa.Numeric(4, 3), nullable=True), if_not_exists=True)
    op.add_column('document_utilities', sa.Column('scoring_metadata', postgresql.JSONB(), nullable=False, server_default='{}'), if_not_exists=True)
    
    # Add indexes for performance
    op.create_index('ix_documents_abstract_fetched_at', 'documents', ['abstract_fetched_at'], if_not_exists=True)
    op.create_index('ix_documents_pub_year', 'documents', ['pub_year'], if_not_exists=True)
    op.create_index('ix_documents_is_open_access', 'documents', ['is_open_access'], if_not_exists=True)
    op.create_index('ix_documents_article_type', 'documents', ['article_type'], if_not_exists=True)
    op.create_index('ix_documents_fulltext_fetched_at', 'documents', ['fulltext_fetched_at'], if_not_exists=True)
    op.create_index('ix_documents_ttl_expires_at', 'documents', ['ttl_expires_at'], if_not_exists=True)
    
    # Add indexes for document_utilities
    op.create_index('idx_document_utilities_stage', 'document_utilities', ['stage'], if_not_exists=True)
    op.create_index('idx_document_utilities_selected', 'document_utilities', ['selected'], if_not_exists=True)
    op.create_index('idx_document_utilities_stage_trial', 'document_utilities', ['trial_id', 'stage'], if_not_exists=True)
    op.create_index('idx_document_utilities_needs_fulltext', 'document_utilities', ['needs_fulltext'], if_not_exists=True)
    op.create_index('idx_document_utilities_fulltext_requested', 'document_utilities', ['fulltext_requested_at'], if_not_exists=True)
    op.create_index('idx_document_utilities_trial_run', 'document_utilities', ['trial_id', 'run_id'], if_not_exists=True)
    op.create_index('idx_document_utilities_stage_selected', 'document_utilities', ['stage', 'selected'], if_not_exists=True)
    op.create_index('idx_document_utilities_u0_score_desc', 'document_utilities', ['u0_score'], postgresql_using='btree', if_not_exists=True)
    
    # Add check constraints
    op.create_check_constraint(
        'ck_document_utilities_stage_range',
        'document_utilities',
        'stage IN (0, 1, 2)',
        if_not_exists=True
    )


def downgrade():
    """Remove Checkpoint 2 & 4 fields from documents and document_utilities tables."""
    
    # Remove indexes first
    op.drop_index('ix_documents_abstract_fetched_at', table_name='documents', if_exists=True)
    op.drop_index('ix_documents_pub_year', table_name='documents', if_exists=True)
    op.drop_index('ix_documents_is_open_access', table_name='documents', if_exists=True)
    op.drop_index('ix_documents_article_type', table_name='documents', if_exists=True)
    op.drop_index('ix_documents_fulltext_fetched_at', table_name='documents', if_exists=True)
    op.drop_index('ix_documents_ttl_expires_at', table_name='documents', if_exists=True)
    
    op.drop_index('idx_document_utilities_stage', table_name='document_utilities', if_exists=True)
    op.drop_index('idx_document_utilities_selected', table_name='document_utilities', if_exists=True)
    op.drop_index('idx_document_utilities_stage_trial', table_name='document_utilities', if_exists=True)
    op.drop_index('idx_document_utilities_needs_fulltext', table_name='document_utilities', if_exists=True)
    op.drop_index('idx_document_utilities_fulltext_requested', table_name='document_utilities', if_exists=True)
    op.drop_index('idx_document_utilities_trial_run', table_name='document_utilities', if_exists=True)
    op.drop_index('idx_document_utilities_stage_selected', table_name='document_utilities', if_exists=True)
    op.drop_index('idx_document_utilities_u0_score_desc', table_name='document_utilities', if_exists=True)
    
    # Remove check constraints
    op.drop_constraint('ck_document_utilities_stage_range', 'document_utilities', type_='check', if_exists=True)
    
    # Remove columns from document_utilities table
    op.drop_column('document_utilities', 'scoring_metadata', if_exists=True)
    op.drop_column('document_utilities', 'uncertainty', if_exists=True)
    op.drop_column('document_utilities', 'fulltext_requested_at', if_exists=True)
    op.drop_column('document_utilities', 'needs_fulltext', if_exists=True)
    op.drop_column('document_utilities', 'abstract_fetched_at', if_exists=True)
    op.drop_column('document_utilities', 'dropped_reason', if_exists=True)
    op.drop_column('document_utilities', 'selected', if_exists=True)
    op.drop_column('document_utilities', 'stage', if_exists=True)
    
    # Remove columns from documents table
    op.drop_column('documents', 'ttl_expires_at', if_exists=True)
    op.drop_column('documents', 'fulltext_fetched_at', if_exists=True)
    op.drop_column('documents', 'fulltext_storage_uri', if_exists=True)
    op.drop_column('documents', 'fulltext_text', if_exists=True)
    op.drop_column('documents', 'is_open_access', if_exists=True)
    op.drop_column('documents', 'pub_year', if_exists=True)
    op.drop_column('documents', 'journal', if_exists=True)
    op.drop_column('documents', 'article_type', if_exists=True)
    op.drop_column('documents', 'pub_types', if_exists=True)
    op.drop_column('documents', 'abstract_fetched_at', if_exists=True)
    op.drop_column('documents', 'abstract_storage_uri', if_exists=True)
    op.drop_column('documents', 'abstract_text', if_exists=True)
