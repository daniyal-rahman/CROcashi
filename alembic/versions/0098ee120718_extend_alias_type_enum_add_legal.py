"""extend alias_type enum add 'legal'

Revision ID: 0098ee120718
Revises: 4a1c3717bf76
Create Date: 2025-08-20 12:10:29.240890

"""

from alembic import op
import sqlalchemy as sa

# Fill these with what Alembic generated for you:
revision = "0098ee120718"
down_revision = "4a1c3717bf76"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add 'legal' to enum alias_type if it doesn't exist (safe/idempotent)
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_enum e
            JOIN pg_type t ON t.oid = e.enumtypid
            WHERE t.typname = 'alias_type' AND e.enumlabel = 'legal'
          ) THEN
            ALTER TYPE alias_type ADD VALUE 'legal';
          END IF;
        END$$;
        """
    )

    # 2) Seed 'legal' aliases for companies that don't already have them.
    # Idempotent: INSERT only when a (company_id, name_norm, 'legal') row is not present.
    # Skip NULL names/norms to avoid inserting empty aliases.
    op.execute(
        """
        INSERT INTO company_aliases (company_id, alias, alias_norm, alias_type)
        SELECT c.company_id, c.name, c.name_norm, 'legal'
        FROM companies c
        LEFT JOIN company_aliases a
          ON a.company_id = c.company_id
         AND a.alias_norm = c.name_norm
         AND a.alias_type = 'legal'
        WHERE a.company_id IS NULL
          AND c.name IS NOT NULL
          AND c.name_norm IS NOT NULL;
        """
    )


def downgrade() -> None:
    # Removing enum values in Postgres is non-trivial and destructive.
    # Leave as a no-op. (If you need a strict downgrade, implement a data migration
    # to update/remove rows referencing 'legal' and recreate the enum.)
    pass
