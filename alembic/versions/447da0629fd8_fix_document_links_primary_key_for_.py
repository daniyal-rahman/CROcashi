"""fix_document_links_primary_key_for_basic_science_papers

Revision ID: 447da0629fd8
Revises: 92c650ab2991
Create Date: 2025-09-08 17:40:20.428817

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '447da0629fd8'
down_revision: Union[str, Sequence[str], None] = '92c650ab2991'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix document_links table to support basic science papers with NULL nct_id and asset_id."""
    
    # Drop the existing primary key constraint
    op.drop_constraint('document_links_pkey', 'document_links', type_='primary')
    
    # Make nct_id nullable (for basic science papers that don't have NCT IDs)
    op.alter_column('document_links', 'nct_id', nullable=True)
    
    # Make asset_id nullable (for basic science papers that don't have specific assets)
    op.alter_column('document_links', 'asset_id', nullable=True)
    
    # Create a new primary key that doesn't include nct_id or asset_id
    # This allows both to be NULL for basic science papers while maintaining uniqueness
    op.create_primary_key(
        'document_links_pkey',
        'document_links',
        ['doc_id', 'trial_id', 'company_id', 'link_type']
    )


def downgrade() -> None:
    """Revert the changes to support basic science papers.
    
    WARNING: This downgrade will fail if there are any NULL nct_id or asset_id values 
    in the document_links table. This is expected behavior since the old schema 
    doesn't support basic science papers without NCT IDs or specific assets.
    
    To downgrade successfully, you must first:
    1. Delete all rows with NULL nct_id or asset_id values
    2. Or update them to have valid values
    """
    
    # Check for NULL values first
    connection = op.get_bind()
    null_nct_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM document_links WHERE nct_id IS NULL")
    ).scalar()
    null_asset_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM document_links WHERE asset_id IS NULL")
    ).scalar()
    
    if null_nct_count > 0 or null_asset_count > 0:
        raise Exception(
            f"Cannot downgrade: Found {null_nct_count} NULL nct_id values and "
            f"{null_asset_count} NULL asset_id values. The old schema doesn't support "
            "basic science papers. Please clean up the data first."
        )
    
    # Drop the new primary key
    op.drop_constraint('document_links_pkey', 'document_links', type_='primary')
    
    # Make asset_id NOT NULL again
    op.alter_column('document_links', 'asset_id', nullable=False)
    
    # Make nct_id NOT NULL again
    op.alter_column('document_links', 'nct_id', nullable=False)
    
    # Restore the original primary key
    op.create_primary_key(
        'document_links_pkey',
        'document_links',
        ['doc_id', 'nct_id', 'trial_id', 'asset_id', 'company_id']
    )
