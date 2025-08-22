"""Add company securities tables and view

This migration adds the company_securities table and v_company_tickers view.
The resolver system tables already exist with a different schema than intended.

Revision ID: 20250124_add_resolver_system_and_company_securities
Revises: 20250124_signals_gates_scores
Create Date: 2025-01-24 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250124_add_resolver_system_and_company_securities'
down_revision = '20250124_signals_gates_scores'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create company_securities table if it doesn't exist
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_securities (
          company_id  BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
          security_id TEXT   NOT NULL,
          linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (company_id, security_id)
        );
    """)
    
    # Ensure security_id column is TEXT type
    op.execute("""
        DO $$
        DECLARE coltype text;
        BEGIN
          SELECT data_type
            INTO coltype
            FROM information_schema.columns
           WHERE table_schema='public'
             AND table_name='company_securities'
             AND column_name='security_id';
          IF coltype IS DISTINCT FROM 'text' THEN
            EXECUTE 'ALTER TABLE company_securities
                     ALTER COLUMN security_id TYPE TEXT
                     USING security_id::text';
          END IF;
        END$$;
    """)
    
    # Create index if it doesn't exist
    op.execute("""
        CREATE INDEX IF NOT EXISTS company_securities_security_id_idx
          ON company_securities (security_id);
    """)
    
    # Create the company tickers view
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
    
    # Note: Resolver system tables already exist with a different schema
    # They were created outside of Alembic and have nct_id/run_id instead of trial_id
    # This migration only handles company_securities setup


def downgrade() -> None:
    # Drop company securities view and table
    op.execute("DROP VIEW IF EXISTS v_company_tickers CASCADE;")
    op.execute("DROP TABLE IF EXISTS company_securities CASCADE;")
    
    # Note: Not dropping resolver tables as they were created outside Alembic
