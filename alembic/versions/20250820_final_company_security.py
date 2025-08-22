"""Final update to company securities link table and view

Revision ID: 20250820_final_company_security
Revises: 20250820b_add_rule_id_to_resolver_det_rules
Create Date: 2025-08-20 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250820_final_company_security'
down_revision = '20250820b_add_rule_id_to_resolver_det_rules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing table and recreate with TEXT FK
    op.execute("DROP TABLE IF EXISTS company_securities")
    
    op.execute("""
        CREATE TABLE company_securities (
          company_id  BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
          security_id TEXT   NOT NULL,
          linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (company_id, security_id)
        );
    """)

    # Create index for performance
    op.execute("""
        CREATE INDEX company_securities_security_id_idx
          ON company_securities (security_id);
    """)

    # Build the view that adapts to your `securities` columns
    op.execute("""
        DO $$
        DECLARE
          has_issuer   boolean;
          has_exchange boolean;
          has_active   boolean;
          sql text;
        BEGIN
          SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='securities' AND column_name='issuer_name'
          ) INTO has_issuer;

          SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='securities' AND column_name='exchange'
          ) INTO has_exchange;

          SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='securities' AND column_name='active'
          ) INTO has_active;

          sql := 'CREATE OR REPLACE VIEW v_company_tickers AS
                  SELECT
                    c.company_id,
                    c.name AS company_name,
                    (s.ticker)::text AS ticker, ' ||
               CASE WHEN has_issuer   THEN ' (s.issuer_name)::text AS issuer_name,'
                                         ELSE ' NULL::text AS issuer_name,' END ||
               CASE WHEN has_exchange THEN ' (s.exchange)::text    AS exchange,'
                                         ELSE ' NULL::text AS exchange,' END ||
               CASE WHEN has_active   THEN ' (s.active)::text      AS active,'
                                         ELSE ' NULL::text AS active,' END ||
               ' (s.security_id)::text AS security_id
                  FROM company_securities cs
                  JOIN companies  c ON c.company_id = cs.company_id
                  JOIN securities s ON (s.security_id)::text = (cs.security_id)::text';

          EXECUTE sql;
        END$$;
    """)


def downgrade() -> None:
    # Drop the view
    op.execute('DROP VIEW IF EXISTS v_company_tickers')
    
    # Revert table to original structure
    op.execute("DROP TABLE IF EXISTS company_securities")
    
    op.execute("""
        CREATE TABLE company_securities (
          company_id BIGINT NOT NULL,
          security_id BIGINT NOT NULL,
          PRIMARY KEY (company_id, security_id),
          FOREIGN KEY (company_id) REFERENCES companies(company_id) ON DELETE CASCADE
        );
    """)
