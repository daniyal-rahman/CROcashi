"""Add text_original field to base_spans table

Revision ID: add_text_original_to_base_spans
Revises: fe02bb9a421d
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_text_original_to_base_spans'
down_revision = 'fe02bb9a421d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add text_original field to base_spans table."""
    # Check if base_spans table exists before trying to modify it
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if 'base_spans' not in inspector.get_table_names():
        print("base_spans table does not exist, skipping migration")
        return
    
    # Add text_original column
    op.add_column('base_spans', sa.Column('text_original', sa.Text(), nullable=True))
    
    # Populate text_original with current text values (as a temporary measure)
    # In practice, this should be done by re-processing the documents
    op.execute("UPDATE base_spans SET text_original = text WHERE text_original IS NULL")
    
    # Make text_original NOT NULL after populating
    op.alter_column('base_spans', 'text_original', nullable=False)
    
    # Add index for text_original
    op.create_index('ix_base_spans_text_original', 'base_spans', ['text_original'])


def downgrade() -> None:
    """Remove text_original field from base_spans table."""
    # Drop index
    op.drop_index('ix_base_spans_text_original', table_name='base_spans')
    
    # Drop column
    op.drop_column('base_spans', 'text_original')
