"""fix metadata to meta conflict

Revision ID: 949dce52fffb
Revises: ac80aa3d9fa9
Create Date: 2024-12-19 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '949dce52fffb'
down_revision = 'ac80aa3d9fa9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename metadata columns to meta to avoid SQLAlchemy conflict."""
    
    # 1. Rename trial_versions.metadata to trial_versions.meta
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trial_versions' AND column_name = 'metadata'
            ) THEN
                ALTER TABLE trial_versions RENAME COLUMN metadata TO meta;
            END IF;
        END $$;
    """)
    
    # 2. Rename signals.metadata to signals.meta
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'signals' AND column_name = 'metadata'
            ) THEN
                ALTER TABLE signals RENAME COLUMN metadata TO meta;
            END IF;
        END $$;
    """)
    
    # 3. Rename signal_evidence.metadata to signal_evidence.meta
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'signal_evidence' AND column_name = 'metadata'
            ) THEN
                ALTER TABLE signal_evidence RENAME COLUMN metadata TO meta;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert meta columns back to metadata."""
    
    # 1. Revert trial_versions.meta to trial_versions.metadata
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trial_versions' AND column_name = 'meta'
            ) THEN
                ALTER TABLE trial_versions RENAME COLUMN meta TO metadata;
            END IF;
        END $$;
    """)
    
    # 2. Revert signals.meta to signals.metadata
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'signals' AND column_name = 'meta'
            ) THEN
                ALTER TABLE signals RENAME COLUMN meta TO metadata;
            END IF;
        END $$;
    """)
    
    # 3. Revert signal_evidence.meta to signal_evidence.metadata
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'signal_evidence' AND column_name = 'meta'
            ) THEN
                ALTER TABLE signal_evidence RENAME COLUMN meta TO metadata;
            END IF;
        END $$;
    """)