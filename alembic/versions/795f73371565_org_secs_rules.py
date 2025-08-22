"""org_secs_rules

Revision ID: 795f73371565
Revises: 335ae80a6228
Create Date: 2025-08-19 17:08:39.775095

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "795f73371565"
down_revision = "335ae80a6228"
branch_labels = None
depends_on = None


def upgrade():
    # --- Company aliases (idempotent) ---------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS company_aliases (
      company_id   BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
      alias        TEXT   NOT NULL,
      created_at   TIMESTAMPTZ DEFAULT now(),
      PRIMARY KEY (company_id, alias)
    );
    CREATE INDEX IF NOT EXISTS idx_company_aliases_alias_trgm
      ON company_aliases USING gin (alias gin_trgm_ops);
    """)

    # --- Company relationships + canonical view ------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS company_relationships (
      parent_company_id BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
      child_company_id  BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
      rel_type          TEXT   NOT NULL DEFAULT 'subsidiary',
      start_date        DATE,
      end_date          DATE,
      created_at        TIMESTAMPTZ DEFAULT now(),
      PRIMARY KEY (parent_company_id, child_company_id, rel_type)
    );
    """)

    # Canonical-rollup view (works whether or not relationships exist yet)
    op.execute("""
    CREATE OR REPLACE VIEW v_company_canonical AS
    WITH RECURSIVE up (company_id, canonical_id) AS (
      -- anchor
      SELECT c.company_id::bigint, c.company_id::bigint
      FROM companies c
      WHERE NOT EXISTS (
        SELECT 1
        FROM company_relationships r
        WHERE r.child_company_id = c.company_id::bigint
          AND r.end_date IS NULL
      )
      UNION ALL
      -- recurse
      SELECT r.child_company_id::bigint, up.canonical_id
      FROM company_relationships r
      JOIN up ON up.company_id = r.parent_company_id::bigint
      WHERE r.end_date IS NULL
    )
    SELECT company_id, canonical_id
    FROM up;
    """)

    # --- Company<->Security link + adaptive view -----------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS company_securities (
      company_id  BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
      security_id TEXT   NOT NULL,
      linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
      PRIMARY KEY (company_id, security_id)
    );
    CREATE INDEX IF NOT EXISTS company_securities_security_id_idx
      ON company_securities (security_id);
    """)

    # Build v_company_tickers based on columns that actually exist in `securities`
    op.execute("""
    DO $$
    DECLARE
      has_issuer   boolean;
      has_exchange boolean;
      has_active   boolean;
      sql          text;
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
             CASE WHEN has_issuer   THEN ' (s.issuer_name)::text AS issuer_name,' ELSE ' NULL::text AS issuer_name,' END ||
             CASE WHEN has_exchange THEN ' (s.exchange)::text    AS exchange,'    ELSE ' NULL::text AS exchange,'    END ||
             CASE WHEN has_active   THEN ' (s.active)::text      AS active,'      ELSE ' NULL::text AS active,'      END ||
             ' (s.security_id)::text AS security_id
                FROM company_securities cs
                JOIN companies  c ON c.company_id = cs.company_id
                JOIN securities s ON (s.security_id)::text = (cs.security_id)::text';

      EXECUTE sql;
    END$$;
    """)

    # --- Deterministic resolver rules ----------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS resolver_det_rules (
      pattern      TEXT PRIMARY KEY,
      company_id   BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
      priority     INT    NOT NULL DEFAULT 100,
      method       TEXT   NOT NULL DEFAULT 'regex',
      created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # Add surrogate PK if missing; keep pattern as natural key for upserts
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = 'public.resolver_det_rules'::regclass
          AND attname  = 'rule_id'
          AND NOT attisdropped
      ) THEN
        ALTER TABLE resolver_det_rules ADD COLUMN rule_id BIGSERIAL;
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.resolver_det_rules'::regclass
          AND contype  = 'p'
      ) THEN
        ALTER TABLE resolver_det_rules
          ADD CONSTRAINT resolver_det_rules_pkey PRIMARY KEY (rule_id);
      END IF;
    END$$;
    CREATE INDEX IF NOT EXISTS ix_resolver_det_rules_priority
      ON resolver_det_rules (priority DESC, rule_id ASC);
    """)

    # Optional seed (only if the companies already exist)
    op.execute("""
    DO $$
    DECLARE
      roche_id BIGINT;
      gen_id   BIGINT;
    BEGIN
      SELECT company_id INTO roche_id
      FROM companies
      WHERE name_norm IN (
        lower(regexp_replace('F. Hoffmann-La Roche Ltd','[^a-z0-9]+',' ','g')),
        lower(regexp_replace('Roche','[^a-z0-9]+',' ','g'))
      )
      ORDER BY company_id LIMIT 1;

      SELECT company_id INTO gen_id
      FROM companies
      WHERE name_norm IN (
        lower(regexp_replace('Genentech, Inc.','[^a-z0-9]+',' ','g')),
        lower(regexp_replace('Genentech','[^a-z0-9]+',' ','g'))
      )
      ORDER BY company_id LIMIT 1;

      IF roche_id IS NOT NULL THEN
        INSERT INTO resolver_det_rules (pattern, company_id, priority, method)
        VALUES
          ('(?i)\\bF\\.?\\s*Hoffmann[-\\s]?La[-\\s]?Roche\\b', roche_id, 10, 'regex'),
          ('(?i)\\bHoffmann[-\\s]?La[-\\s]?Roche\\b',          roche_id, 15, 'regex'),
          ('(?i)\\bRoche\\b',                                  roche_id, 30, 'regex')
        ON CONFLICT (pattern) DO UPDATE
          SET company_id=EXCLUDED.company_id, priority=EXCLUDED.priority;
      END IF;

      IF gen_id IS NOT NULL THEN
        INSERT INTO resolver_det_rules (pattern, company_id, priority, method)
        VALUES
          ('(?i)\\bGenentech\\b',             gen_id, 10, 'regex'),
          ('(?i)\\bGenentech,\\s*Inc\\.?\\b', gen_id, 10, 'regex')
        ON CONFLICT (pattern) DO UPDATE
          SET company_id=EXCLUDED.company_id, priority=EXCLUDED.priority;
      END IF;
    END$$;
    """)


def downgrade():
    op.execute("DROP VIEW IF EXISTS v_company_tickers;")
    op.execute("DROP TABLE IF EXISTS company_securities;")
    op.execute("DROP VIEW IF EXISTS v_company_canonical;")
    op.execute("DROP TABLE IF EXISTS company_relationships;")
    op.execute("DROP TABLE IF EXISTS company_aliases;")
    op.execute("DROP TABLE IF EXISTS resolver_det_rules;")
