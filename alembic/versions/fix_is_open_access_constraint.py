"""Fix is_open_access constraint to allow NULL values

Revision ID: fix_is_open_access_constraint
Revises: 1e2bd3801e0d
Create Date: 2025-08-28 14:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fix_is_open_access_constraint'
down_revision = '1e2bd3801e0d'
branch_labels = None
depends_on = None


def upgrade():
    """Fix is_open_access constraint to allow NULL values."""
    
    # Drop the existing column and recreate it as nullable
    # This is needed because we can't easily change NOT NULL to NULL in PostgreSQL
    
    # First, drop the column
    op.drop_column('documents', 'is_open_access')
    
    # Then recreate it as nullable with default
    op.add_column('documents', sa.Column('is_open_access', sa.Boolean(), nullable=True, server_default='false'))


def downgrade():
    """Revert is_open_access constraint back to NOT NULL."""
    
    # Drop the nullable column
    op.drop_column('documents', 'is_open_access')
    
    # Recreate it as NOT NULL with default
    op.add_column('documents', sa.Column('is_open_access', sa.Boolean(), nullable=False, server_default='false'))
