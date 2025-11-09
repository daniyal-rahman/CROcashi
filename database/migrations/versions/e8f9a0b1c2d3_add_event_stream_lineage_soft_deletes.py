"""add event stream lineage soft deletes

Revision ID: e8f9a0b1c2d3
Revises: 47bf175203a3
Create Date: 2025-11-07 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = '47bf175203a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add soft delete columns to all existing tables
    # This is a comprehensive list - add deleted_at and deletion_reason to all BaseModel tables
    
    tables_with_soft_delete = [
        'companies', 'institutions', 'drugs', 'drug_chemical_identity', 'drug_names',
        'targets', 'mechanisms', 'diseases', 'disease_names',
        'clinical_trials', 'trial_status_history', 'regulatory_events',
        'publications', 'patents', 'conferences', 'conference_presentations', 'sec_filings',
        'company_ownership_history', 'company_drugs', 'drug_ownership_history',
        'drug_targets', 'drug_mechanisms', 'drug_indications', 'drug_combinations',
        'trial_sponsors', 'trial_funding', 'trial_drugs', 'trial_diseases',
        'publication_drugs', 'publication_trials', 'publication_companies',
        'patent_drugs', 'patent_companies',
        'regulatory_drug_events', 'regulatory_company_events',
        'presentation_drugs', 'presentation_companies', 'presentation_trials',
        'filing_companies', 'filing_drugs',
        'entity_aliases', 'entity_matches', 'entity_match_confidence',
        'matching_review_queue', 'entity_match_candidates', 'entity_matching_rules',
        'source_processing_log', 'data_quality_metrics', 'staging_raw_data'
    ]
    
    for table_name in tables_with_soft_delete:
        # Check if columns already exist (for idempotency)
        conn = op.get_bind()
        inspector = sa.inspect(conn)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        
        if 'deleted_at' not in columns:
            op.add_column(
                table_name,
                sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
            )
            op.create_index(f'ix_{table_name}_deleted_at', table_name, ['deleted_at'])
        
        if 'deletion_reason' not in columns:
            op.add_column(
                table_name,
                sa.Column('deletion_reason', sa.Text, nullable=True)
            )
    
    # Add temporal tracking to entity_aliases
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    entity_aliases_columns = [col['name'] for col in inspector.get_columns('entity_aliases')]
    
    if 'valid_from' not in entity_aliases_columns:
        op.add_column('entity_aliases', sa.Column('valid_from', sa.Date, nullable=True))
        op.create_index('ix_entity_aliases_valid_from', 'entity_aliases', ['valid_from'])
    
    if 'valid_to' not in entity_aliases_columns:
        op.add_column('entity_aliases', sa.Column('valid_to', sa.Date, nullable=True))
        op.create_index('ix_entity_aliases_valid_to', 'entity_aliases', ['valid_to'])
    
    # Create sources table
    op.create_table(
        'sources',
        sa.Column('source_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('source_name', sa.String(200), nullable=False, unique=True),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('reliability_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('update_frequency', sa.String(50), nullable=True),
        sa.Column('last_checked', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('base_url', sa.String(1000), nullable=True),
        sa.Column('documentation_url', sa.String(1000), nullable=True),
        sa.Column('source_metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text, nullable=True),
        sa.CheckConstraint(
            "source_type IN ('regulatory', 'literature', 'financial', 'social', 'patent', 'clinical', 'other')",
            name='check_source_type'
        ),
        sa.CheckConstraint(
            "update_frequency IN ('daily', 'weekly', 'monthly', 'on_demand', 'real_time') OR update_frequency IS NULL",
            name='check_update_frequency'
        ),
        sa.CheckConstraint(
            "reliability_score IS NULL OR (reliability_score >= 0 AND reliability_score <= 1)",
            name='check_reliability_score'
        ),
    )
    op.create_index('ix_sources_source_id', 'sources', ['source_id'])
    op.create_index('ix_sources_source_name', 'sources', ['source_name'])
    op.create_index('ix_sources_source_type', 'sources', ['source_type'])
    op.create_index('ix_sources_deleted_at', 'sources', ['deleted_at'])
    
    # Create data_lineage table
    op.create_table(
        'data_lineage',
        sa.Column('lineage_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('table_name', sa.String(200), nullable=False),
        sa.Column('record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('extracted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('raw_data_snapshot', postgresql.JSONB, nullable=True),
        sa.Column('extraction_method', sa.String(50), nullable=True),
        sa.Column('extraction_metadata', postgresql.JSONB, nullable=True),
        sa.Column('confidence_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text, nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['sources.source_id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "extraction_method IN ('manual', 'api', 'scraper', 'llm', 'parser', 'other') OR extraction_method IS NULL",
            name='check_extraction_method'
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name='check_lineage_confidence_score'
        ),
    )
    op.create_index('ix_data_lineage_lineage_id', 'data_lineage', ['lineage_id'])
    op.create_index('ix_data_lineage_table_name', 'data_lineage', ['table_name'])
    op.create_index('ix_data_lineage_record_id', 'data_lineage', ['record_id'])
    op.create_index('ix_data_lineage_source_id', 'data_lineage', ['source_id'])
    op.create_index('ix_data_lineage_extracted_at', 'data_lineage', ['extracted_at'])
    op.create_index('ix_data_lineage_deleted_at', 'data_lineage', ['deleted_at'])
    
    # Create entity_merges table
    op.create_table(
        'entity_merges',
        sa.Column('merge_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('source_entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('merged_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('merge_reason', sa.Text, nullable=True),
        sa.Column('reversible', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('merged_by', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text, nullable=True),
        sa.CheckConstraint(
            "entity_type IN ('company', 'drug', 'disease', 'target', 'institution', 'trial', 'publication', 'patent')",
            name='check_merge_entity_type'
        ),
    )
    op.create_index('ix_entity_merges_merge_id', 'entity_merges', ['merge_id'])
    op.create_index('ix_entity_merges_source_entity_id', 'entity_merges', ['source_entity_id'])
    op.create_index('ix_entity_merges_target_entity_id', 'entity_merges', ['target_entity_id'])
    op.create_index('ix_entity_merges_entity_type', 'entity_merges', ['entity_type'])
    op.create_index('ix_entity_merges_merged_by', 'entity_merges', ['merged_by'])
    op.create_index('ix_entity_merges_deleted_at', 'entity_merges', ['deleted_at'])
    
    # Create events table
    op.create_table(
        'events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('event_type', sa.String(200), nullable=False),
        sa.Column('event_significance', sa.String(20), nullable=False),
        sa.Column('event_date', sa.Date, nullable=False),
        sa.Column('entities_involved', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column('event_data', postgresql.JSONB, nullable=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('confidence_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('discovered_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('related_event_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deletion_reason', sa.Text, nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['sources.source_id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "event_significance IN ('critical', 'major', 'minor', 'trace')",
            name='check_event_significance'
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name='check_event_confidence_score'
        ),
    )
    op.create_index('ix_events_event_id', 'events', ['event_id'])
    op.create_index('ix_events_event_type', 'events', ['event_type'])
    op.create_index('ix_events_event_significance', 'events', ['event_significance'])
    op.create_index('ix_events_event_date', 'events', ['event_date'])
    op.create_index('ix_events_source_id', 'events', ['source_id'])
    op.create_index('ix_events_discovered_at', 'events', ['discovered_at'])
    op.create_index('ix_events_deleted_at', 'events', ['deleted_at'])
    
    # Create GIN index on events.event_data for JSONB queries
    op.execute('CREATE INDEX IF NOT EXISTS ix_events_event_data ON events USING GIN (event_data)')
    
    # Create GIN index on events.entities_involved for efficient array queries
    op.execute('CREATE INDEX IF NOT EXISTS ix_events_entities_involved ON events USING GIN (entities_involved)')
    
    # Create GIN index on data_lineage.raw_data_snapshot
    op.execute('CREATE INDEX IF NOT EXISTS ix_data_lineage_raw_data_snapshot ON data_lineage USING GIN (raw_data_snapshot)')


def downgrade() -> None:
    # Drop indexes
    op.execute('DROP INDEX IF EXISTS ix_data_lineage_raw_data_snapshot')
    op.execute('DROP INDEX IF EXISTS ix_events_entities_involved')
    op.execute('DROP INDEX IF EXISTS ix_events_event_data')
    
    # Drop events table
    op.drop_index('ix_events_deleted_at', table_name='events')
    op.drop_index('ix_events_discovered_at', table_name='events')
    op.drop_index('ix_events_source_id', table_name='events')
    op.drop_index('ix_events_event_date', table_name='events')
    op.drop_index('ix_events_event_significance', table_name='events')
    op.drop_index('ix_events_event_type', table_name='events')
    op.drop_index('ix_events_event_id', table_name='events')
    op.drop_table('events')
    
    # Drop entity_merges table
    op.drop_index('ix_entity_merges_deleted_at', table_name='entity_merges')
    op.drop_index('ix_entity_merges_merged_by', table_name='entity_merges')
    op.drop_index('ix_entity_merges_entity_type', table_name='entity_merges')
    op.drop_index('ix_entity_merges_target_entity_id', table_name='entity_merges')
    op.drop_index('ix_entity_merges_source_entity_id', table_name='entity_merges')
    op.drop_index('ix_entity_merges_merge_id', table_name='entity_merges')
    op.drop_table('entity_merges')
    
    # Drop data_lineage table
    op.drop_index('ix_data_lineage_deleted_at', table_name='data_lineage')
    op.drop_index('ix_data_lineage_extracted_at', table_name='data_lineage')
    op.drop_index('ix_data_lineage_source_id', table_name='data_lineage')
    op.drop_index('ix_data_lineage_record_id', table_name='data_lineage')
    op.drop_index('ix_data_lineage_table_name', table_name='data_lineage')
    op.drop_index('ix_data_lineage_lineage_id', table_name='data_lineage')
    op.drop_table('data_lineage')
    
    # Drop sources table
    op.drop_index('ix_sources_deleted_at', table_name='sources')
    op.drop_index('ix_sources_source_type', table_name='sources')
    op.drop_index('ix_sources_source_name', table_name='sources')
    op.drop_index('ix_sources_source_id', table_name='sources')
    op.drop_table('sources')
    
    # Remove temporal tracking from entity_aliases
    op.drop_index('ix_entity_aliases_valid_to', table_name='entity_aliases')
    op.drop_index('ix_entity_aliases_valid_from', table_name='entity_aliases')
    op.drop_column('entity_aliases', 'valid_to')
    op.drop_column('entity_aliases', 'valid_from')
    
    # Remove soft delete columns from all tables
    tables_with_soft_delete = [
        'companies', 'institutions', 'drugs', 'drug_chemical_identity', 'drug_names',
        'targets', 'mechanisms', 'diseases', 'disease_names',
        'clinical_trials', 'trial_status_history', 'regulatory_events',
        'publications', 'patents', 'conferences', 'conference_presentations', 'sec_filings',
        'company_ownership_history', 'company_drugs', 'drug_ownership_history',
        'drug_targets', 'drug_mechanisms', 'drug_indications', 'drug_combinations',
        'trial_sponsors', 'trial_funding', 'trial_drugs', 'trial_diseases',
        'publication_drugs', 'publication_trials', 'publication_companies',
        'patent_drugs', 'patent_companies',
        'regulatory_drug_events', 'regulatory_company_events',
        'presentation_drugs', 'presentation_companies', 'presentation_trials',
        'filing_companies', 'filing_drugs',
        'entity_aliases', 'entity_matches', 'entity_match_confidence',
        'matching_review_queue', 'entity_match_candidates', 'entity_matching_rules',
        'source_processing_log', 'data_quality_metrics', 'staging_raw_data'
    ]
    
    for table_name in tables_with_soft_delete:
        try:
            op.drop_index(f'ix_{table_name}_deleted_at', table_name=table_name)
            op.drop_column(table_name, 'deletion_reason')
            op.drop_column(table_name, 'deleted_at')
        except Exception:
            # Ignore if columns don't exist
            pass

