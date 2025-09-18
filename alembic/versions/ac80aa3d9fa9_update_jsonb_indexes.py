"""update jsonb indexes

Revision ID: ac80aa3d9fa9
Revises: ec190b7db457
Create Date: 2024-12-19 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ac80aa3d9fa9'
down_revision = 'ec190b7db457'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Update indexes to reflect renamed JSONB fields."""
    
    # Drop old index on names_jsonb (now renamed to names)
    op.execute("DROP INDEX IF EXISTS idx_assets_names_jsonb")
    
    # Create new index on names
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_assets_names'
            ) THEN
                CREATE INDEX idx_assets_names ON assets USING gin (names);
            END IF;
        END $$;
    """)
    
    # Drop old index on extracted_jsonb (now renamed to extracted_data)
    op.execute("DROP INDEX IF EXISTS idx_studies_extracted_jsonb")
    
    # Create new index on extracted_data
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_studies_extracted_data'
            ) THEN
                CREATE INDEX idx_studies_extracted_data ON studies USING gin (extracted_data);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert indexes to use old JSONB field names."""
    
    # Drop new indexes
    op.execute("DROP INDEX IF EXISTS idx_assets_names")
    op.execute("DROP INDEX IF EXISTS idx_studies_extracted_data")
    
    # Note: The old indexes will be recreated when the columns are renamed back
    # This is handled by the main JSONB rename migration