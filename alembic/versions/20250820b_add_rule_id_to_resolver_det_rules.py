"""Add rule_id column to resolver_det_rules table

Revision ID: 20250820b_add_rule_id_to_resolver_det_rules
Revises: 20250820_resolver_det_rules
Create Date: 2025-08-20 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250820b_add_rule_id_to_resolver_det_rules'
down_revision = '20250820_resolver_det_rules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add a surrogate PK column expected by the code
    op.execute("""
        ALTER TABLE resolver_det_rules
          ADD COLUMN IF NOT EXISTS rule_id BIGSERIAL;
    """)

    # If there's no PK yet, make rule_id the PK
    op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = 'public.resolver_det_rules'::regclass
              AND contype = 'p'
          ) THEN
            ALTER TABLE resolver_det_rules
              ADD CONSTRAINT resolver_det_rules_pkey PRIMARY KEY (rule_id);
          END IF;
        END$$;
    """)

    # Helpful index for the query plan the code uses
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_resolver_det_rules_priority
          ON resolver_det_rules (priority DESC, rule_id ASC);
    """)


def downgrade() -> None:
    # Drop the index
    op.execute("DROP INDEX IF EXISTS ix_resolver_det_rules_priority")
    
    # Drop the primary key constraint if it was added
    op.execute("""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = 'public.resolver_det_rules'::regclass
              AND contype = 'p'
              AND constraint_name = 'resolver_det_rules_pkey'
          ) THEN
            ALTER TABLE resolver_det_rules
              DROP CONSTRAINT resolver_det_rules_pkey;
          END IF;
        END$$;
    """)
    
    # Drop the rule_id column
    op.execute("ALTER TABLE resolver_det_rules DROP COLUMN IF EXISTS rule_id")
