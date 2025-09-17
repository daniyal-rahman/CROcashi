"""fix_spans_and_rename_tables

Revision ID: 6d9da568e3fd
Revises: f2ba019967c2
Create Date: 2025-09-15 19:39:09.347495

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d9da568e3fd'
down_revision: Union[str, Sequence[str], None] = 'f2ba019967c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix spans and rename tables."""
    # Step 1: Remove unused span tables (idempotent - check if tables exist first)
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()
    
    if 'base_span_derived_span_association' in existing_tables:
        op.drop_table('base_span_derived_span_association')
    if 'base_spans' in existing_tables:
        op.drop_table('base_spans')
    if 'derived_spans' in existing_tables:
        op.drop_table('derived_spans')
    
    # Step 2: Rename existing tables
    op.rename_table('method_cards', 'study_cards')
    op.rename_table('results_factsheets', 'factsheets')
    op.rename_table('evidence_spans', 'spans')
    
    # Step 3: Add new columns to study_cards for versioning
    op.add_column('study_cards', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('study_cards', sa.Column('authored_by', sa.String(), nullable=True))
    op.add_column('study_cards', sa.Column('model_name', sa.String(), nullable=True))
    op.add_column('study_cards', sa.Column('p_fail', sa.Float(), nullable=True))
    op.add_column('study_cards', sa.Column('gates_json', sa.JSON(), nullable=True))
    op.add_column('study_cards', sa.Column('summary_text', sa.Text(), nullable=True))
    op.add_column('study_cards', sa.Column('risks_text', sa.Text(), nullable=True))
    op.add_column('study_cards', sa.Column('methods_text', sa.Text(), nullable=True))
    
    # Add check constraint for authored_by
    op.create_check_constraint(
        'ck_study_cards_authored_by',
        'study_cards',
        "authored_by IS NULL OR authored_by IN ('llm', 'human')"
    )
    
    # Step 4: Simplify spans table (remove unused columns)
    op.drop_column('spans', 'line_start')
    op.drop_column('spans', 'line_end')
    op.drop_column('spans', 'table_header_ids')
    op.drop_column('spans', 'figure_id')
    op.drop_column('spans', 'supplementary_id')
    op.drop_column('spans', 'kind')
    op.drop_column('spans', 'parent_span_ids')
    op.drop_column('spans', 'internal_id')
    op.drop_column('spans', 'status')
    op.drop_column('spans', 'span_metadata')
    op.drop_column('spans', 'updated_at')
    
    # Step 5: Add new columns to spans
    op.add_column('spans', sa.Column('snippet_hash', sa.String(), nullable=True))
    op.add_column('spans', sa.Column('bbox_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Step 5: Remove new columns from spans
    op.drop_column('spans', 'bbox_json')
    op.drop_column('spans', 'snippet_hash')
    
    # Step 4: Restore removed columns to spans
    op.add_column('spans', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')))
    op.add_column('spans', sa.Column('span_metadata', sa.JSON(), nullable=True))
    op.add_column('spans', sa.Column('status', sa.String(), nullable=True))
    op.add_column('spans', sa.Column('internal_id', sa.String(), nullable=True))
    op.add_column('spans', sa.Column('parent_span_ids', sa.JSON(), nullable=True))
    op.add_column('spans', sa.Column('kind', sa.String(), nullable=True))
    op.add_column('spans', sa.Column('supplementary_id', sa.String(), nullable=True))
    op.add_column('spans', sa.Column('figure_id', sa.String(), nullable=True))
    op.add_column('spans', sa.Column('table_header_ids', sa.JSON(), nullable=True))
    op.add_column('spans', sa.Column('line_end', sa.Integer(), nullable=True))
    op.add_column('spans', sa.Column('line_start', sa.Integer(), nullable=True))
    
    # Step 3: Remove new columns from study_cards
    op.drop_constraint('ck_study_cards_authored_by', 'study_cards', type_='check')
    op.drop_column('study_cards', 'methods_text')
    op.drop_column('study_cards', 'risks_text')
    op.drop_column('study_cards', 'summary_text')
    op.drop_column('study_cards', 'gates_json')
    op.drop_column('study_cards', 'p_fail')
    op.drop_column('study_cards', 'model_name')
    op.drop_column('study_cards', 'authored_by')
    op.drop_column('study_cards', 'version')
    
    # Step 2: Rename tables back
    op.rename_table('spans', 'evidence_spans')
    op.rename_table('factsheets', 'results_factsheets')
    op.rename_table('study_cards', 'method_cards')
    
    # Step 1: Recreate unused span tables
    from sqlalchemy.dialects import postgresql as psql
    
    # Recreate base_spans table
    op.create_table(
        'base_spans',
        sa.Column('span_id', sa.Integer, nullable=False, autoincrement=True),
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('section', sa.Text, nullable=False),
        sa.Column('page', sa.Integer, nullable=True),
        sa.Column('char_start', sa.Integer, nullable=False),
        sa.Column('char_end', sa.Integer, nullable=False),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('text_original', sa.Text, nullable=False),
        sa.Column('is_table_cell', sa.Boolean, nullable=False, default=False),
        sa.Column('table_id', sa.Integer, nullable=True),
        sa.Column('row', sa.Integer, nullable=True),
        sa.Column('col', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('span_id'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        sa.CheckConstraint("char_end > char_start", name="ck_base_spans_char_range"),
        sa.CheckConstraint("char_start >= 0", name="ck_base_spans_char_start_positive"),
    )
    op.create_index('ix_base_spans_doc_id', 'base_spans', ['doc_id'])
    op.create_index('ix_base_spans_section', 'base_spans', ['section'])
    op.create_index('ix_base_spans_page', 'base_spans', ['page'])
    op.create_index('ix_base_spans_char_range', 'base_spans', ['char_start', 'char_end'])
    op.create_index('ix_base_spans_table', 'base_spans', ['table_id', 'row', 'col'])
    op.create_index('ix_base_spans_text_original', 'base_spans', ['text_original'])
    
    # Recreate derived_spans table
    op.create_table(
        'derived_spans',
        sa.Column('derived_id', sa.Integer, nullable=False, autoincrement=True),
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('char_start', sa.Integer, nullable=False),
        sa.Column('char_end', sa.Integer, nullable=False),
        sa.Column('parent_span_ids', psql.ARRAY(sa.Integer), nullable=False),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('similarity_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('derived_id'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        sa.CheckConstraint("char_end > char_start", name="ck_derived_spans_char_range"),
        sa.CheckConstraint("char_start >= 0", name="ck_derived_spans_char_start_positive"),
        sa.CheckConstraint("similarity_score >= 0.0 AND similarity_score <= 1.0", name="ck_derived_spans_similarity_range"),
    )
    op.create_index('ix_derived_spans_doc_id', 'derived_spans', ['doc_id'])
    op.create_index('ix_derived_spans_char_range', 'derived_spans', ['char_start', 'char_end'])
    op.create_index('ix_derived_spans_parent_ids', 'derived_spans', ['parent_span_ids'], postgresql_using='gin')
    
    # Recreate association table
    op.create_table(
        'base_span_derived_span_association',
        sa.Column('base_span_id', sa.Integer, nullable=False),
        sa.Column('derived_span_id', sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint('base_span_id', 'derived_span_id'),
        sa.ForeignKeyConstraint(['base_span_id'], ['base_spans.span_id']),
        sa.ForeignKeyConstraint(['derived_span_id'], ['derived_spans.derived_id']),
    )
    op.create_index('ix_base_derived_assoc_base', 'base_span_derived_span_association', ['base_span_id'])
    op.create_index('ix_base_derived_assoc_derived', 'base_span_derived_span_association', ['derived_span_id'])
