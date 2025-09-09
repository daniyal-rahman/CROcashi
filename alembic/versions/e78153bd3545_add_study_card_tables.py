"""add_study_card_tables

Revision ID: e78153bd3545
Revises: 447da0629fd8
Create Date: 2025-09-08 21:39:27.026432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e78153bd3545'
down_revision: Union[str, Sequence[str], None] = '447da0629fd8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create method_cards table
    op.create_table('method_cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('doc_id', sa.String(), nullable=False),
        sa.Column('design_archetype', sa.String(), nullable=True),
        sa.Column('is_blinded', sa.Boolean(), nullable=True),
        sa.Column('analysis_set', sa.String(), nullable=True),
        sa.Column('population_description', sa.Text(), nullable=True),
        sa.Column('stratification_factors', sa.JSON(), nullable=True),
        sa.Column('covariate_adjustment', sa.JSON(), nullable=True),
        sa.Column('primary_endpoint', sa.Text(), nullable=True),
        sa.Column('secondary_endpoints', sa.JSON(), nullable=True),
        sa.Column('summary_measure', sa.String(), nullable=True),
        sa.Column('alpha_level', sa.Float(), nullable=True),
        sa.Column('is_one_sided', sa.Boolean(), nullable=True),
        sa.Column('multiplicity_adjustment', sa.String(), nullable=True),
        sa.Column('sample_size_reassessment', sa.Boolean(), nullable=True),
        sa.Column('interim_looks', sa.JSON(), nullable=True),
        sa.Column('interim_timing', sa.String(), nullable=True),
        sa.Column('spending_function', sa.String(), nullable=True),
        sa.Column('stop_rules', sa.JSON(), nullable=True),
        sa.Column('missingness_assumption', sa.String(), nullable=True),
        sa.Column('missingness_pattern', sa.String(), nullable=True),
        sa.Column('imputation_method', sa.String(), nullable=True),
        sa.Column('estimand', sa.Text(), nullable=True),
        sa.Column('intercurrent_events_policy', sa.Text(), nullable=True),
        sa.Column('endpoint_ascertainment', sa.String(), nullable=True),
        sa.Column('assessment_interval', sa.String(), nullable=True),
        sa.Column('adjudication_committee', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create results_factsheets table
    op.create_table('results_factsheets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('doc_id', sa.String(), nullable=False),
        sa.Column('results', sa.JSON(), nullable=True),
        sa.Column('primary_endpoint_results', sa.JSON(), nullable=True),
        sa.Column('secondary_endpoint_results', sa.JSON(), nullable=True),
        sa.Column('safety_results', sa.JSON(), nullable=True),
        sa.Column('primary_analysis_set', sa.String(), nullable=True),
        sa.Column('secondary_analysis_sets', sa.JSON(), nullable=True),
        sa.Column('total_enrolled', sa.Integer(), nullable=True),
        sa.Column('completed_primary_endpoint', sa.Integer(), nullable=True),
        sa.Column('dropout_rate', sa.Float(), nullable=True),
        sa.Column('follow_up_completion', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create gate_assessments table
    op.create_table('gate_assessments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gate_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('p_gate', sa.Float(), nullable=True),
        sa.Column('rationale', sa.JSON(), nullable=True),
        sa.Column('sensitivity', sa.JSON(), nullable=True),
        sa.Column('computed_values', sa.JSON(), nullable=True),
        sa.Column('threshold_comparisons', sa.JSON(), nullable=True),
        sa.Column('assessment_method', sa.String(), nullable=True),
        sa.Column('confidence_in_assessment', sa.Float(), nullable=True),
        sa.Column('assessment_notes', sa.JSON(), nullable=True),
        sa.Column('next_steps', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create evidence_spans table
    op.create_table('evidence_spans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('doc_id', sa.String(), nullable=False),
        sa.Column('quote', sa.Text(), nullable=False),
        sa.Column('section', sa.String(), nullable=False),
        sa.Column('page', sa.Integer(), nullable=True),
        sa.Column('char_start', sa.Integer(), nullable=True),
        sa.Column('char_end', sa.Integer(), nullable=True),
        sa.Column('line_start', sa.Integer(), nullable=True),
        sa.Column('line_end', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('table_id', sa.String(), nullable=True),
        sa.Column('table_row', sa.Integer(), nullable=True),
        sa.Column('table_col', sa.Integer(), nullable=True),
        sa.Column('table_header_ids', sa.JSON(), nullable=True),
        sa.Column('figure_id', sa.String(), nullable=True),
        sa.Column('supplementary_id', sa.String(), nullable=True),
        sa.Column('kind', sa.String(), nullable=True),
        sa.Column('parent_span_ids', sa.JSON(), nullable=True),
        sa.Column('internal_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('span_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('evidence_spans')
    op.drop_table('gate_assessments')
    op.drop_table('results_factsheets')
    op.drop_table('method_cards')
