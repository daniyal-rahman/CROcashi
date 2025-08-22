"""enhance_study_card_schema_phase2

Revision ID: cb8dbc1fff5f
Revises: 7a372ed1b33a
Create Date: 2025-08-22 13:15:29.481240

Enhance study card schema with additional fields for comprehensive analysis:
- tone_analysis: Overall tone and claim strength analysis
- conflicts_and_funding: Conflict of interest and funding information
- publication_details: Journal information and registry discrepancies
- data_location_mapping: Enhanced evidence location tracking
- reviewer_notes: Limitations, oddities, and quality assessments

This migration adds new JSONB columns to the studies table for storing
the enhanced study card data while maintaining backward compatibility.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'cb8dbc1fff5f'
down_revision: Union[str, Sequence[str], None] = '7a372ed1b33a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    try:
        result = op.get_bind().execute(sa.text("""
            SELECT COUNT(*) 
            FROM information_schema.columns 
            WHERE table_name = :table_name 
            AND column_name = :column_name
        """), {"table_name": table_name, "column_name": column_name})
        return result.scalar() > 0
    except Exception:
        return False


def upgrade() -> None:
    """Upgrade schema to add enhanced study card fields."""
    
    # Add tone_analysis column for storing tone and claim strength analysis
    if not column_exists('studies', 'tone_analysis'):
        op.add_column('studies', sa.Column(
            'tone_analysis', 
            postgresql.JSONB(astext_type=sa.Text()), 
            nullable=True,
            comment='Tone and claim strength analysis data'
        ))
    
    # Add conflicts_and_funding column for COI and funding information
    if not column_exists('studies', 'conflicts_and_funding'):
        op.add_column('studies', sa.Column(
            'conflicts_and_funding', 
            postgresql.JSONB(astext_type=sa.Text()), 
            nullable=True,
            comment='Conflicts of interest and funding source information'
        ))
    
    # Add publication_details column for journal and publication metadata
    if not column_exists('studies', 'publication_details'):
        op.add_column('studies', sa.Column(
            'publication_details', 
            postgresql.JSONB(astext_type=sa.Text()), 
            nullable=True,
            comment='Publication metadata including journal type and registry discrepancies'
        ))
    
    # Add data_location_mapping column for enhanced evidence tracking
    if not column_exists('studies', 'data_location_mapping'):
        op.add_column('studies', sa.Column(
            'data_location_mapping', 
            postgresql.JSONB(astext_type=sa.Text()), 
            nullable=True,
            comment='Enhanced data location mapping with tables, figures, and quote spans'
        ))
    
    # Add reviewer_notes column for limitations and quality assessments
    if not column_exists('studies', 'reviewer_notes'):
        op.add_column('studies', sa.Column(
            'reviewer_notes', 
            postgresql.JSONB(astext_type=sa.Text()), 
            nullable=True,
            comment='Reviewer notes including limitations, oddities, and quality assessments'
        ))
    
    # Create indexes on the new JSONB columns for better query performance
    try:
        op.create_index(
            'ix_studies_tone_analysis_gin',
            'studies',
            ['tone_analysis'],
            postgresql_using='gin',
            if_not_exists=True
        )
    except Exception:
        pass  # Index might already exist
    
    try:
        op.create_index(
            'ix_studies_conflicts_funding_gin',
            'studies',
            ['conflicts_and_funding'],
            postgresql_using='gin',
            if_not_exists=True
        )
    except Exception:
        pass  # Index might already exist
    
    try:
        op.create_index(
            'ix_studies_publication_details_gin',
            'studies',
            ['publication_details'],
            postgresql_using='gin',
            if_not_exists=True
        )
    except Exception:
        pass  # Index might already exist
    
    try:
        op.create_index(
            'ix_studies_data_location_gin',
            'studies',
            ['data_location_mapping'],
            postgresql_using='gin',
            if_not_exists=True
        )
    except Exception:
        pass  # Index might already exist
    
    try:
        op.create_index(
            'ix_studies_reviewer_notes_gin',
            'studies',
            ['reviewer_notes'],
            postgresql_using='gin',
            if_not_exists=True
        )
    except Exception:
        pass  # Index might already exist
    
    # Create a view for enhanced study card analysis
    op.execute(sa.text("""
        CREATE OR REPLACE VIEW v_enhanced_study_cards AS
        SELECT 
            s.study_id,
            s.trial_id,
            s.extracted_jsonb,
            s.coverage_level,
            s.tone_analysis,
            s.conflicts_and_funding,
            s.publication_details,
            s.data_location_mapping,
            s.reviewer_notes,
            -- Extract commonly used fields for easier querying
            s.tone_analysis->>'overall_tone' as overall_tone,
            s.publication_details->>'journal_type' as journal_type,
            s.publication_details->>'open_access' as open_access,
            s.reviewer_notes->'quality_assessment'->>'overall_quality' as reviewer_quality_rating,
            s.reviewer_notes->'quality_assessment'->>'evidence_strength' as evidence_strength,
            -- Count various elements
            jsonb_array_length(COALESCE(s.conflicts_and_funding->'conflicts_of_interest', '[]'::jsonb)) as conflicts_count,
            jsonb_array_length(COALESCE(s.conflicts_and_funding->'funding_sources', '[]'::jsonb)) as funding_sources_count,
            jsonb_array_length(COALESCE(s.reviewer_notes->'limitations', '[]'::jsonb)) as limitations_count,
            jsonb_array_length(COALESCE(s.reviewer_notes->'oddities', '[]'::jsonb)) as oddities_count,
            jsonb_array_length(COALESCE(s.data_location_mapping->'quote_spans', '[]'::jsonb)) as quote_spans_count,
            s.created_at,
            s.updated_at
        FROM studies s
        WHERE s.extracted_jsonb IS NOT NULL;
    """))


def downgrade() -> None:
    """Downgrade schema by removing enhanced study card fields."""
    
    # Drop the view first
    op.execute(sa.text("DROP VIEW IF EXISTS v_enhanced_study_cards;"))
    
    # Drop indexes
    try:
        op.drop_index('ix_studies_reviewer_notes_gin', table_name='studies')
    except Exception:
        pass
    
    try:
        op.drop_index('ix_studies_data_location_gin', table_name='studies')
    except Exception:
        pass
    
    try:
        op.drop_index('ix_studies_publication_details_gin', table_name='studies')
    except Exception:
        pass
    
    try:
        op.drop_index('ix_studies_conflicts_funding_gin', table_name='studies')
    except Exception:
        pass
    
    try:
        op.drop_index('ix_studies_tone_analysis_gin', table_name='studies')
    except Exception:
        pass
    
    # Drop columns (only if they exist)
    if column_exists('studies', 'reviewer_notes'):
        op.drop_column('studies', 'reviewer_notes')
    
    if column_exists('studies', 'data_location_mapping'):
        op.drop_column('studies', 'data_location_mapping')
    
    if column_exists('studies', 'publication_details'):
        op.drop_column('studies', 'publication_details')
    
    if column_exists('studies', 'conflicts_and_funding'):
        op.drop_column('studies', 'conflicts_and_funding')
    
    if column_exists('studies', 'tone_analysis'):
        op.drop_column('studies', 'tone_analysis')
