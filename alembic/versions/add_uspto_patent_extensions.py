"""Add USPTO patent extensions

Revision ID: add_uspto_patent_extensions
Revises: 9d2e40215ede
Create Date: 2024-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_uspto_patent_extensions'
down_revision: Union[str, None] = '9d2e40215ede'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = '8f4433c1c1aa'


def upgrade() -> None:
    # Create patents table first
    op.create_table('patents',
        sa.Column('patent_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('family_id', sa.Text(), nullable=True),
        sa.Column('jurisdiction', sa.Text(), nullable=False),
        sa.Column('number', sa.Text(), nullable=False),
        sa.Column('earliest_priority_date', sa.Date(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('assignees', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('inventors', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('links_jsonb', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='SET NULL', name='fk_patents_asset_id_assets'),
        sa.PrimaryKeyConstraint('patent_id', name='pk_patents'),
        sa.UniqueConstraint('jurisdiction', 'number', name='uq_patents_jurisdiction_number')
    )
    
    # Create patent_assignments table
    op.create_table('patent_assignments',
        sa.Column('assignment_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('patent_id', sa.BigInteger(), nullable=False),
        sa.Column('assignor', sa.Text(), nullable=False),
        sa.Column('assignee', sa.Text(), nullable=False),
        sa.Column('exec_date', sa.Date(), nullable=True),
        sa.Column('record_date', sa.Date(), nullable=True),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['patent_id'], ['patents.patent_id'], ondelete='CASCADE', name='fk_patent_assignments_patent_id_patents'),
        sa.PrimaryKeyConstraint('assignment_id', name='pk_patent_assignments')
    )
    
    # Create indexes for patents table
    op.create_index('idx_patents_asset_id', 'patents', ['asset_id'])
    op.create_index('idx_patents_earliest_priority_date', 'patents', ['earliest_priority_date'])
    
    # Create indexes for patent_assignments table
    op.create_index('idx_patent_assignments_patent_id', 'patent_assignments', ['patent_id'])
    op.create_index('idx_patent_assignments_exec_date', 'patent_assignments', ['exec_date'])
    
    # Create patent families table
    op.create_table('patent_families',
        sa.Column('family_id', sa.String(), nullable=False),
        sa.Column('earliest_priority_date', sa.Date(), nullable=True),
        sa.Column('patent_count', sa.Integer(), nullable=True),
        sa.Column('us_patent_count', sa.Integer(), nullable=True),
        sa.Column('family_type', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('family_id', name='pk_patent_families')
    )
    
    # Create patent family members table
    op.create_table('patent_family_members',
        sa.Column('family_id', sa.String(), nullable=False),
        sa.Column('patent_id', sa.BigInteger(), nullable=False),
        sa.Column('priority_date', sa.Date(), nullable=True),
        sa.Column('publication_date', sa.Date(), nullable=True),
        sa.Column('is_priority_document', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['family_id'], ['patent_families.family_id'], name='fk_patent_family_members_family_id_patent_families'),
        sa.ForeignKeyConstraint(['patent_id'], ['patents.patent_id'], name='fk_patent_family_members_patent_id_patents'),
        sa.PrimaryKeyConstraint('family_id', 'patent_id', name='pk_patent_family_members')
    )
    
    # Create asset-patent links table
    op.create_table('asset_patent_links',
        sa.Column('link_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('patent_id', sa.BigInteger(), nullable=False),
        sa.Column('link_confidence', sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column('link_method', sa.String(), nullable=False),
        sa.Column('evidence_spans', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='CASCADE', name='fk_asset_patent_links_asset_id_assets'),
        sa.ForeignKeyConstraint(['patent_id'], ['patents.patent_id'], ondelete='CASCADE', name='fk_asset_patent_links_patent_id_patents'),
        sa.PrimaryKeyConstraint('link_id', name='pk_asset_patent_links'),
        sa.CheckConstraint('link_confidence >= 0.0 AND link_confidence <= 1.0', name='ck_asset_patent_links_confidence_range'),
        sa.CheckConstraint("link_method IN ('inn_exact', 'code_mention', 'text_similarity', 'assignee_temporal', 'manual')", name='ck_asset_patent_links_method')
    )
    
    # Create ownership snapshots table
    op.create_table('ownership_snapshots',
        sa.Column('snapshot_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('owner_company_id', sa.Integer(), nullable=False),
        sa.Column('ownership_type', sa.String(), nullable=False),
        sa.Column('ownership_percentage', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('evidence_source', sa.String(), nullable=False),
        sa.Column('evidence_url', sa.String(), nullable=True),
        sa.Column('confidence_score', sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.asset_id'], ondelete='CASCADE', name='fk_ownership_snapshots_asset_id_assets'),
        sa.ForeignKeyConstraint(['owner_company_id'], ['companies.company_id'], ondelete='CASCADE', name='fk_ownership_snapshots_owner_company_id_companies'),
        sa.PrimaryKeyConstraint('snapshot_id', name='pk_ownership_snapshots'),
        sa.CheckConstraint("ownership_type IN ('assignee', 'licensee', 'co_owner', 'inventor', 'applicant')", name='ck_ownership_snapshots_type'),
        sa.CheckConstraint("evidence_source IN ('patent_assignment', 'sec_filing', 'press_release', 'clinical_trial', 'manual')", name='ck_ownership_snapshots_source'),
        sa.CheckConstraint('confidence_score >= 0.0 AND confidence_score <= 1.0', name='ck_ownership_snapshots_confidence_range')
    )
    
    # Add columns to existing patent_assignments table
    op.add_column('patent_assignments', sa.Column('assignment_type_detail', sa.String(), nullable=True))
    op.add_column('patent_assignments', sa.Column('execution_amount', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('patent_assignments', sa.Column('consideration_type', sa.String(), nullable=True))
    op.add_column('patent_assignments', sa.Column('sec_exhibit_reference', sa.String(), nullable=True))
    op.add_column('patent_assignments', sa.Column('assignment_text', sa.Text(), nullable=True))
    op.add_column('patent_assignments', sa.Column('parsed_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Add constraint for consideration_type
    op.create_check_constraint(
        'ck_patent_assignments_consideration_type',
        'patent_assignments',
        "consideration_type IS NULL OR consideration_type IN ('monetary', 'equity', 'licensing', 'merger', 'other')"
    )
    
    # Add indexes for performance
    op.create_index('idx_patent_families_earliest_priority', 'patent_families', ['earliest_priority_date'])
    op.create_index('idx_patent_family_members_priority_date', 'patent_family_members', ['priority_date'])
    op.create_index('idx_asset_patent_links_asset_id', 'asset_patent_links', ['asset_id'])
    op.create_index('idx_asset_patent_links_patent_id', 'asset_patent_links', ['patent_id'])
    op.create_index('idx_asset_patent_links_confidence', 'asset_patent_links', ['link_confidence'])
    op.create_index('idx_ownership_snapshots_asset_date', 'ownership_snapshots', ['asset_id', 'as_of_date'])
    op.create_index('idx_ownership_snapshots_owner_id', 'ownership_snapshots', ['owner_company_id'])
    op.create_index('idx_ownership_snapshots_evidence_source', 'ownership_snapshots', ['evidence_source'])
    
    # Add indexes for patent assignments new columns
    op.create_index('idx_patent_assignments_execution_amount', 'patent_assignments', ['execution_amount'])
    op.create_index('idx_patent_assignments_consideration_type', 'patent_assignments', ['consideration_type'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_patent_assignments_consideration_type')
    op.drop_index('idx_patent_assignments_execution_amount')
    op.drop_index('idx_ownership_snapshots_evidence_source')
    op.drop_index('idx_ownership_snapshots_owner_id')
    op.drop_index('idx_ownership_snapshots_asset_date')
    op.drop_index('idx_asset_patent_links_confidence')
    op.drop_index('idx_asset_patent_links_patent_id')
    op.drop_index('idx_asset_patent_links_asset_id')
    op.drop_index('idx_patent_family_members_priority_date')
    op.drop_index('idx_patent_families_earliest_priority')
    op.drop_index('idx_patent_assignments_exec_date')
    op.drop_index('idx_patent_assignments_patent_id')
    op.drop_index('idx_patents_earliest_priority_date')
    op.drop_index('idx_patents_asset_id')
    
    # Drop constraint
    op.drop_constraint('ck_patent_assignments_consideration_type', 'patent_assignments')
    
    # Drop added columns
    op.drop_column('patent_assignments', 'parsed_metadata')
    op.drop_column('patent_assignments', 'assignment_text')
    op.drop_column('patent_assignments', 'sec_exhibit_reference')
    op.drop_column('patent_assignments', 'consideration_type')
    op.drop_column('patent_assignments', 'execution_amount')
    op.drop_column('patent_assignments', 'assignment_type_detail')
    
    # Drop tables
    op.drop_table('ownership_snapshots')
    op.drop_table('asset_patent_links')
    op.drop_table('patent_family_members')
    op.drop_table('patent_families')
    op.drop_table('patent_assignments')
    op.drop_table('patents')
