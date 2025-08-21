"""Add how column to StudyAssetsXref (idempotent)

Revision ID: 20250121_add_how_to_study_assets_xref
Revises: 20250121_fix_trial_assets_xref_trial_id
Create Date: 2025-01-21 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20250121_add_how_to_study_assets_xref"
down_revision: Union[str, Sequence[str], None] = "20250121_fix_trial_assets_xref_trial_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: only act if table exists; only add/alter when needed.
    op.execute(
        """
        DO $$
        BEGIN
          -- If the table is present
          IF EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'study_assets_xref'
          ) THEN

            -- Add the column if missing
            IF NOT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = 'study_assets_xref'
                AND column_name = 'how'
            ) THEN
              ALTER TABLE public.study_assets_xref ADD COLUMN how text;
            END IF;

            -- Backfill NULLs to a sensible placeholder
            UPDATE public.study_assets_xref
               SET how = 'legacy_migration'
             WHERE how IS NULL;

            -- Make NOT NULL only if currently nullable and no NULLs remain
            IF EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = 'study_assets_xref'
                AND column_name = 'how'
                AND is_nullable = 'YES'
            ) THEN
              IF NOT EXISTS (SELECT 1 FROM public.study_assets_xref WHERE how IS NULL) THEN
                ALTER TABLE public.study_assets_xref ALTER COLUMN how SET NOT NULL;
              END IF;
            END IF;

          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # Idempotent: drop only if it exists (and table exists)
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'study_assets_xref'
          ) THEN
            IF EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = 'study_assets_xref'
                AND column_name = 'how'
            ) THEN
              ALTER TABLE public.study_assets_xref DROP COLUMN how;
            END IF;
          END IF;
        END$$;
        """
    )
