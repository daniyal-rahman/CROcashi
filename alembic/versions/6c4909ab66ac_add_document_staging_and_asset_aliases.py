"""add_document_staging_and_asset_aliases

Revision ID: 6c4909ab66ac
Revises: 91c4a47ab949
Create Date: 2025-08-26 12:16:42.498450

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6c4909ab66ac'
down_revision: Union[str, Sequence[str], None] = '91c4a47ab949'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    
    # Create source_type enum for documents
    source_type_enum = postgresql.ENUM(
        'PR', 'IR', 'SEC', 'Registry', 'Abstract', 'Poster', 'Paper', 'FDA', 'Patent',
        name='source_type_enum',
        create_type=True
    )
    source_type_enum.create(op.get_bind())
    
    # Create status enum for documents
    status_enum = postgresql.ENUM(
        'discovered', 'fetched', 'parsed', 'linked', 'failed',
        name='document_status_enum',
        create_type=True
    )
    status_enum.create(op.get_bind())
    
    # Create entity_type enum for document_entities
    entity_type_enum = postgresql.ENUM(
        'asset_code', 'inn', 'generic', 'company', 'ticker', 'nct', 'endpoint', 'indication', 'moa', 'target', 'code',
        name='entity_type_enum',
        create_type=True
    )
    entity_type_enum.create(op.get_bind())
    
    # Create alias_type enum for asset_aliases
    alias_type_enum = postgresql.ENUM(
        'inn', 'internal_code', 'generic', 'brand', 'misspelling', 'db_id', 'code',
        name='asset_alias_type_enum',
        create_type=True
    )
    alias_type_enum.create(op.get_bind())
    
    # Create documents table (raw/staging) - MATCHING CODE USAGE
    op.create_table('documents',
        sa.Column('doc_id', sa.Integer, primary_key=True, autoincrement=True),  # Changed from UUID to Integer to match code
        sa.Column('source_type', sa.Text, nullable=False),
        sa.Column('source_url', sa.Text, nullable=True),  # Changed from 'url' to 'source_url' to match code
        sa.Column('url_hash', sa.Text, nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('parsed_at', sa.DateTime(timezone=True), nullable=True),  # Added to match code
        sa.Column('linked_at', sa.DateTime(timezone=True), nullable=True),  # Added to match code
        sa.Column('content_type', sa.Text, nullable=True),  # Changed from 'mime_type' to 'content_type' to match code
        sa.Column('title', sa.Text, nullable=True),
        sa.Column('doi', sa.Text, nullable=True),
        sa.Column('pmid', sa.Text, nullable=True),
        sa.Column('pmcid', sa.Text, nullable=True),
        sa.Column('nct_id', sa.Text, nullable=True),
        sa.Column('sponsor_text', sa.Text, nullable=True),
        sa.Column('status', sa.Text, nullable=False, server_default='discovered'),
        sa.Column('error_text', sa.Text, nullable=True),
        sa.Column('storage_uri', sa.Text, nullable=True),  # Changed from 'storage_path' to 'storage_uri' to match code
        sa.Column('sha256', sa.Text, nullable=True),  # Changed from 'text_hash' to 'sha256' to match code
        sa.Column('publisher', sa.Text, nullable=True),  # Added to match code
        sa.CheckConstraint("source_type::text = ANY (ARRAY['PR','IR','SEC','Registry','Abstract','Poster','Paper','FDA','Patent']::text[])", name='ck_documents_source_type'),
        sa.CheckConstraint("status::text = ANY (ARRAY['discovered','fetched','parsed','linked','failed']::text[])", name='ck_documents_status')
    )
    
    # Create indexes for documents
    op.create_index('ix_documents_lower_doi', 'documents', [sa.func.lower(sa.func.coalesce(sa.text("doi"), ''))])
    op.create_index('ix_documents_lower_pmid', 'documents', [sa.func.lower(sa.func.coalesce(sa.text("pmid"), ''))])
    op.create_index('ix_documents_lower_pmcid', 'documents', [sa.func.lower(sa.func.coalesce(sa.text("pmcid"), ''))])
    op.create_index('ix_documents_lower_nct_id', 'documents', [sa.func.lower(sa.func.coalesce(sa.text("nct_id"), ''))])
    op.create_index('ix_documents_published_at', 'documents', ['published_at'])
    op.create_index('ix_documents_url_hash', 'documents', ['url_hash'], unique=True)
    op.create_index('ix_documents_sha256', 'documents', ['sha256'])  # Changed from 'text_hash' to 'sha256'
    op.create_index('ix_documents_source_url', 'documents', ['source_url'])  # Added to match code
    
    # Create document_text_pages table - MATCHING CODE USAGE
    op.create_table('document_text_pages',
        sa.Column('doc_id', sa.Integer, nullable=False),  # Changed from UUID to Integer
        sa.Column('page_no', sa.Integer, nullable=False),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('char_count', sa.Integer, nullable=True),  # Added to match code
        sa.PrimaryKeyConstraint('doc_id', 'page_no'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE')
    )
    
    # Create document_tables table - MATCHING CODE USAGE
    op.create_table('document_tables',
        sa.Column('doc_id', sa.Integer, nullable=False),  # Changed from UUID to Integer
        sa.Column('page_no', sa.Integer, nullable=False),  # Added to match code
        sa.Column('table_idx', sa.Integer, nullable=False),
        sa.Column('caption', sa.Text, nullable=True),
        sa.Column('table_jsonb', postgresql.JSONB, nullable=True),  # Changed from 'data_jsonb' to 'table_jsonb' to match code
        sa.Column('detector', sa.Text, nullable=True),  # Added to match code
        sa.PrimaryKeyConstraint('doc_id', 'table_idx'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE')
    )
    
    # Create document_citations table - MATCHING CODE USAGE
    op.create_table('document_citations',
        sa.Column('doc_id', sa.Integer, nullable=False),  # Changed from UUID to Integer
        sa.Column('doi', sa.Text, nullable=True),  # Changed to match code structure
        sa.Column('pmid', sa.Text, nullable=True),  # Changed to match code structure
        sa.Column('pmcid', sa.Text, nullable=True),  # Changed to match code structure
        sa.Column('nct_id', sa.Text, nullable=True),  # Changed to match code structure
        sa.PrimaryKeyConstraint('doc_id'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE')
    )
    
    # Create document_entities table - MATCHING CODE USAGE
    op.create_table('document_entities',
        sa.Column('doc_id', sa.Integer, nullable=False),  # Changed from UUID to Integer
        sa.Column('ent_type', sa.Text, nullable=False),  # Changed from 'entity_type' to 'ent_type' to match code
        sa.Column('value_text', sa.Text, nullable=False),  # Changed from 'value' to 'value_text' to match code
        sa.Column('value_norm', sa.Text, nullable=True),  # Changed from 'norm_value' to 'value_norm' to match code
        sa.Column('page_no', sa.Integer, nullable=False),  # Added to match code
        sa.Column('char_start', sa.Integer, nullable=False),  # Changed from 'span_start' to 'char_start' to match code
        sa.Column('char_end', sa.Integer, nullable=False),  # Changed from 'span_end' to 'char_end' to match code
        sa.Column('detector', sa.Text, nullable=True),  # Added to match code
        sa.Column('confidence', sa.Numeric, nullable=True),
        sa.PrimaryKeyConstraint('doc_id', 'ent_type', 'value_text', 'char_start'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        sa.CheckConstraint("ent_type::text = ANY (ARRAY['asset_code','inn','generic','company','ticker','nct','endpoint','indication','moa','target','code']::text[])", name='ck_document_entities_ent_type')
    )
    
    # Create document_links table - MATCHING CODE USAGE
    op.create_table('document_links',
        sa.Column('doc_id', sa.Integer, nullable=False),  # Changed from UUID to Integer
        sa.Column('nct_id', sa.Text, nullable=True),  # Added to match code
        sa.Column('trial_id', sa.Integer, nullable=True),
        sa.Column('asset_id', sa.Integer, nullable=True),
        sa.Column('company_id', sa.Integer, nullable=True),
        sa.Column('link_type', sa.Text, nullable=True),  # Added to match code
        sa.Column('confidence', sa.Numeric, nullable=True),
        sa.Column('heuristics', postgresql.JSONB, nullable=True),
        sa.Column('evidence_json', postgresql.JSONB, nullable=True),
        sa.PrimaryKeyConstraint('doc_id', 'nct_id', 'trial_id', 'asset_id', 'company_id'),  # Updated to include nct_id
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name='ck_document_links_confidence_range')
    )
    
    # Create document_notes table - ADDED TO MATCH CODE
    op.create_table('document_notes',
        sa.Column('note_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('note_type', sa.Text, nullable=False),
        sa.Column('note_text', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE')
    )
    
    # Create asset_aliases table - MATCHING CODE USAGE
    op.create_table('asset_aliases',
        sa.Column('asset_alias_id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('asset_id', sa.Integer, nullable=False),
        sa.Column('alias', sa.Text, nullable=False),
        sa.Column('alias_norm', sa.Text, nullable=True),  # Added to match code
        sa.Column('alias_type', sa.Text, nullable=False),
        sa.Column('source', sa.Text, nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='CASCADE'),
        sa.CheckConstraint("alias_type::text = ANY (ARRAY['inn','internal_code','generic','brand','misspelling','db_id','code']::text[])", name='ck_asset_aliases_alias_type')
    )
    
    # Create unique constraint for asset aliases (case-insensitive)
    op.create_index('ix_asset_aliases_lower_alias', 'asset_aliases', [sa.func.lower('alias')], unique=True)
    op.create_index('ix_asset_aliases_asset_id', 'asset_aliases', ['asset_id'])
    op.create_index('ix_asset_aliases_alias_norm', 'asset_aliases', ['alias_norm'])  # Added to match code
    
    # Add doc_id column to studies table for provenance
    op.add_column('studies', sa.Column('doc_id', sa.Integer, nullable=True))  # Changed from UUID to Integer
    op.create_index('ix_studies_doc_id', 'studies', ['doc_id'])
    op.create_foreign_key('fk_studies_documents', 'studies', 'documents', ['doc_id'], ['doc_id'], ondelete='SET NULL')
    
    # Rename hash column to text_hash for consistency
    op.alter_column('studies', 'hash', new_column_name='text_hash')
    
    # Update the unique constraint to use text_hash
    # First check if the constraint exists, then drop it
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    constraints = inspector.get_unique_constraints('studies')
    constraint_names = [c['name'] for c in constraints]
    
    if 'uq_studies_hash_notnull' in constraint_names:
        op.drop_constraint('uq_studies_hash_notnull', 'studies', type_='unique')
    
    # Create the new unique constraint (simplified without WHERE clause)
    op.create_unique_constraint('uq_studies_text_hash_notnull', 'studies', ['text_hash'])


def downgrade() -> None:
    """Downgrade schema."""
    
    # Remove foreign key and column from studies
    op.drop_constraint('fk_studies_documents', 'studies', type_='foreignkey')
    op.drop_index('ix_studies_doc_id', 'studies')
    op.drop_column('studies', 'doc_id')
    
    # Revert hash column name
    op.alter_column('studies', 'text_hash', new_column_name='hash')
    
    # Revert unique constraint - check if it exists first
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    constraints = inspector.get_unique_constraints('studies')
    constraint_names = [c['name'] for c in constraints]
    
    if 'uq_studies_text_hash_notnull' in constraint_names:
        op.drop_constraint('uq_studies_text_hash_notnull', 'studies', type_='unique')
    
    # Create the original unique constraint (simplified without WHERE clause)
    op.create_unique_constraint('uq_studies_hash_notnull', 'studies', ['hash'])
    
    # Drop tables in reverse order
    op.drop_table('document_notes')
    op.drop_table('document_links')
    op.drop_table('document_entities')
    op.drop_table('document_citations')
    op.drop_table('document_tables')
    op.drop_table('document_text_pages')
    op.drop_table('asset_aliases')
    op.drop_table('documents')
    
    # Drop enums
    op.execute('DROP TYPE asset_alias_type_enum')
    op.execute('DROP TYPE entity_type_enum')
    op.execute('DROP TYPE document_status_enum')
    op.execute('DROP TYPE source_type_enum')
