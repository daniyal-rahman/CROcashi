"""Fix selected constraint to allow NULL values

Revision ID: fix_selected_constraint
Revises: fix_is_open_access_constraint
Create Date: 2025-08-28 14:40:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fix_selected_constraint'
down_revision = 'fix_is_open_access_constraint'
branch_labels = None
depends_on = None


def upgrade():
    """Fix selected constraint to allow NULL values."""
    
    # Drop the existing column and recreate it as nullable
    # This is needed because we can't easily change NOT NULL to NULL in PostgreSQL
    
    # First, drop the column
    op.drop_column('document_utilities', 'selected')
    
    # Then recreate it as nullable with default
    op.add_column('document_utilities', sa.Column('selected', sa.Boolean(), nullable=True, server_default='false'))


def downgrade():
    """Revert selected constraint back to NOT NULL."""
    
    # Drop the nullable column
    op.drop_column('document_utilities', 'selected')
    
    # Recreate it as NOT NULL with default
    op.add_column('document_utilities', sa.Column('selected', sa.Boolean(), nullable=False, server_default='false'))
