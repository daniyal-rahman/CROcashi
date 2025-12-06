"""add entity resolution tables

Revision ID: c8d9a1b2e3f4
Revises: b7faf67a03a0
Create Date: 2025-11-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c8d9a1b2e3f4'
down_revision: Union[str, None] = 'b7faf67a03a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add entity resolution tables for the processing pipeline."""
    
    # Create entity_match_candidates table
    op.create_table(
        'entity_match_candidates',
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False, comment='company, drug, disease, target, trial, publication'),
        sa.Column('source_identifier', sa.String(500), nullable=False, comment='e.g., NCT number, PMID, accession number'),
        sa.Column('source_name', sa.String(200), nullable=False, comment='ClinicalTrials.gov, PubMed, FDA, SEC'),
        sa.Column('extracted_text', sa.String(1000), nullable=False, comment='The name/text extracted from source'),
        sa.Column('extracted_context', postgresql.JSONB, nullable=True, comment='Additional context for matching'),
        sa.Column('potential_matches', postgresql.JSONB, nullable=True, comment='Array of {"entity_id": "...", "score": 0.85, "reason": "..."}'),
        sa.Column('matched_to', postgresql.UUID(as_uuid=True), nullable=True, comment='Final canonical entity_id'),
        sa.Column('match_confidence', sa.Numeric(3, 2), nullable=True, comment='0.0 to 1.0'),
        sa.Column('match_method', sa.String(50), nullable=True, comment='exact_identifier, exact_name, alias, fuzzy_context, manual'),
        sa.Column('match_reasoning', sa.Text, nullable=True, comment='Explanation of why this match was made'),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending', comment='pending, auto_matched, needs_review, reviewed, new_entity'),
        sa.Column('reviewed_by', sa.String(200), nullable=True),
        sa.Column('reviewed_at', sa.Date, nullable=True),
        sa.Column('review_notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('company', 'drug', 'disease', 'target', 'trial', 'publication', 'institution')",
            name='check_candidate_entity_type'
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'auto_matched', 'needs_review', 'reviewed', 'new_entity')",
            name='check_candidate_status'
        ),
        sa.CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name='check_candidate_confidence'
        ),
        comment='Entity match candidates for resolution pipeline'
    )
    
    # Create indexes for entity_match_candidates
    op.create_index('ix_entity_match_candidates_candidate_id', 'entity_match_candidates', ['candidate_id'])
    op.create_index('ix_entity_match_candidates_entity_type', 'entity_match_candidates', ['entity_type'])
    op.create_index('ix_entity_match_candidates_source_identifier', 'entity_match_candidates', ['source_identifier'])
    op.create_index('ix_entity_match_candidates_source_name', 'entity_match_candidates', ['source_name'])
    op.create_index('ix_entity_match_candidates_matched_to', 'entity_match_candidates', ['matched_to'])
    op.create_index('ix_entity_match_candidates_match_method', 'entity_match_candidates', ['match_method'])
    op.create_index('ix_entity_match_candidates_status', 'entity_match_candidates', ['status'])
    op.create_index('ix_entity_match_candidates_reviewed_at', 'entity_match_candidates', ['reviewed_at'])
    
    # Create entity_matching_rules table
    op.create_table(
        'entity_matching_rules',
        sa.Column('rule_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False, comment='company, drug, disease, target, trial'),
        sa.Column('matching_strategy', sa.String(50), nullable=False, comment='exact_identifier, exact_name, fuzzy_name, context_aware, alias'),
        sa.Column('priority', sa.Integer, nullable=False, comment='Order to try strategies (1 = highest priority)'),
        sa.Column('config', postgresql.JSONB, nullable=True, comment='e.g., {"threshold": 0.85, "use_context": true, "context_weight": 0.3}'),
        sa.Column('active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('last_modified', sa.Date, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('company', 'drug', 'disease', 'target', 'trial', 'publication', 'institution')",
            name='check_rule_entity_type'
        ),
        sa.CheckConstraint(
            "matching_strategy IN ('exact_identifier', 'exact_name', 'fuzzy_name', 'context_aware', 'alias')",
            name='check_matching_strategy'
        ),
        comment='Configurable entity matching rules'
    )
    
    # Create indexes for entity_matching_rules
    op.create_index('ix_entity_matching_rules_rule_id', 'entity_matching_rules', ['rule_id'])
    op.create_index('ix_entity_matching_rules_entity_type', 'entity_matching_rules', ['entity_type'])
    op.create_index('ix_entity_matching_rules_matching_strategy', 'entity_matching_rules', ['matching_strategy'])
    op.create_index('ix_entity_matching_rules_priority', 'entity_matching_rules', ['priority'])
    op.create_index('ix_entity_matching_rules_active', 'entity_matching_rules', ['active'])
    
    # Create source_processing_log table
    op.create_table(
        'source_processing_log',
        sa.Column('log_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('source_name', sa.String(200), nullable=False, comment='clinicaltrials_gov, fda_drugs, sec_edgar, pubmed'),
        sa.Column('source_identifier', sa.String(500), nullable=False, comment='Specific record ID (NCT#, PMID, etc.)'),
        sa.Column('processing_started_at', sa.Date, nullable=False),
        sa.Column('processing_completed_at', sa.Date, nullable=True),
        sa.Column('processing_status', sa.String(50), nullable=False, server_default='processing', comment='success, partial, failed, needs_review'),
        sa.Column('entities_extracted', sa.Integer, nullable=True),
        sa.Column('entities_matched', sa.Integer, nullable=True),
        sa.Column('entities_created', sa.Integer, nullable=True),
        sa.Column('relationships_created', sa.Integer, nullable=True),
        sa.Column('warnings', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('errors', postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column('processing_details', postgresql.JSONB, nullable=True, comment='Detailed processing information'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "processing_status IN ('processing', 'success', 'partial', 'failed', 'needs_review')",
            name='check_processing_status'
        ),
        comment='Source processing audit log'
    )
    
    # Create indexes for source_processing_log
    op.create_index('ix_source_processing_log_log_id', 'source_processing_log', ['log_id'])
    op.create_index('ix_source_processing_log_source_name', 'source_processing_log', ['source_name'])
    op.create_index('ix_source_processing_log_source_identifier', 'source_processing_log', ['source_identifier'])
    op.create_index('ix_source_processing_log_processing_started_at', 'source_processing_log', ['processing_started_at'])
    op.create_index('ix_source_processing_log_processing_completed_at', 'source_processing_log', ['processing_completed_at'])
    op.create_index('ix_source_processing_log_processing_status', 'source_processing_log', ['processing_status'])
    op.create_index('ix_source_processing_log_source_status', 'source_processing_log', ['source_name', 'processing_status'])
    
    # Create GIN indexes for JSONB columns for better query performance
    op.create_index('ix_entity_match_candidates_extracted_context_gin', 'entity_match_candidates', ['extracted_context'], postgresql_using='gin')
    op.create_index('ix_entity_match_candidates_potential_matches_gin', 'entity_match_candidates', ['potential_matches'], postgresql_using='gin')
    op.create_index('ix_entity_matching_rules_config_gin', 'entity_matching_rules', ['config'], postgresql_using='gin')
    op.create_index('ix_source_processing_log_processing_details_gin', 'source_processing_log', ['processing_details'], postgresql_using='gin')


def downgrade() -> None:
    """Remove entity resolution tables."""
    
    # Drop indexes
    op.drop_index('ix_source_processing_log_processing_details_gin', 'source_processing_log')
    op.drop_index('ix_entity_matching_rules_config_gin', 'entity_matching_rules')
    op.drop_index('ix_entity_match_candidates_potential_matches_gin', 'entity_match_candidates')
    op.drop_index('ix_entity_match_candidates_extracted_context_gin', 'entity_match_candidates')
    
    op.drop_index('ix_source_processing_log_source_status', 'source_processing_log')
    op.drop_index('ix_source_processing_log_processing_status', 'source_processing_log')
    op.drop_index('ix_source_processing_log_processing_completed_at', 'source_processing_log')
    op.drop_index('ix_source_processing_log_processing_started_at', 'source_processing_log')
    op.drop_index('ix_source_processing_log_source_identifier', 'source_processing_log')
    op.drop_index('ix_source_processing_log_source_name', 'source_processing_log')
    op.drop_index('ix_source_processing_log_log_id', 'source_processing_log')
    
    op.drop_index('ix_entity_matching_rules_active', 'entity_matching_rules')
    op.drop_index('ix_entity_matching_rules_priority', 'entity_matching_rules')
    op.drop_index('ix_entity_matching_rules_matching_strategy', 'entity_matching_rules')
    op.drop_index('ix_entity_matching_rules_entity_type', 'entity_matching_rules')
    op.drop_index('ix_entity_matching_rules_rule_id', 'entity_matching_rules')
    
    op.drop_index('ix_entity_match_candidates_reviewed_at', 'entity_match_candidates')
    op.drop_index('ix_entity_match_candidates_status', 'entity_match_candidates')
    op.drop_index('ix_entity_match_candidates_match_method', 'entity_match_candidates')
    op.drop_index('ix_entity_match_candidates_matched_to', 'entity_match_candidates')
    op.drop_index('ix_entity_match_candidates_source_name', 'entity_match_candidates')
    op.drop_index('ix_entity_match_candidates_source_identifier', 'entity_match_candidates')
    op.drop_index('ix_entity_match_candidates_entity_type', 'entity_match_candidates')
    op.drop_index('ix_entity_match_candidates_candidate_id', 'entity_match_candidates')
    
    # Drop tables
    op.drop_table('source_processing_log')
    op.drop_table('entity_matching_rules')
    op.drop_table('entity_match_candidates')

