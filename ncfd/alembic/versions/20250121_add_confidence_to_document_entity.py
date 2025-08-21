"""Add confidence field to document_entities (idempotent)

Revision ID: 20250121_add_confidence_to_document_entity
Revises: 20250121_create_final_xref_tables
Create Date: 2025-01-21 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20250121_add_confidence_to_document_entity"
down_revision: Union[str, Sequence[str], None] = "20250121_create_final_xref_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # Idempotent: add column only if table exists and column is missing
    # -------------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'document_entities'
            ) THEN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'document_entities'
                      AND column_name = 'confidence'
                ) THEN
                    ALTER TABLE public.document_entities
                    ADD COLUMN confidence numeric(3,2);
                END IF;

                -- Add check constraint only if missing
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_document_entities_confidence'
                ) THEN
                    ALTER TABLE public.document_entities
                    ADD CONSTRAINT ck_document_entities_confidence
                    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
                END IF;
            END IF;
        END$$;
        """
    )

    # Create index if not exists (Postgres supports IF NOT EXISTS)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_entities_confidence "
        "ON public.document_entities (confidence);"
    )


def downgrade() -> None:
    # Drop index/constraint/column if they exist (idempotent)
    op.execute(
        "DROP INDEX IF EXISTS ix_document_entities_confidence;"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'document_entities'
            ) THEN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_document_entities_confidence'
                ) THEN
                    ALTER TABLE public.document_entities
                    DROP CONSTRAINT IF EXISTS ck_document_entities_confidence;
                END IF;

                ALTER TABLE public.document_entities
                DROP COLUMN IF EXISTS confidence;
            END IF;
        END$$;
        """
    )
