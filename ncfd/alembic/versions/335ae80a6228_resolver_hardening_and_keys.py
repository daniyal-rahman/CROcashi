"""resolver_hardening_and_keys

- resolver_features: dedupe + unique(run_id,nct_id,company_id) + created_at + idx (if table exists)
- resolver_decisions: ensure cols + unique(run_id,nct_id,sponsor_text_norm)

Revision ID: 335ae80a6228
Revises: 924b9867b702
Create Date: 2025-08-19
"""
from alembic import op
import sqlalchemy as sa


revision = "335ae80a6228"
down_revision = "924b9867b702"
branch_labels = None
depends_on = None


def upgrade():
    # --- resolver_features hardening (only if table exists) ---
    # We guard with to_regclass so upgrades don't fail on fresh DBs
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.resolver_features') IS NOT NULL THEN
            -- Deduplicate existing rows before unique key
            WITH ranked AS (
              SELECT ctid,
                     row_number() OVER (
                       PARTITION BY run_id, nct_id, company_id
                       ORDER BY COALESCE(p_calibrated, score_precal, 0) DESC, ctid DESC
                     ) AS rn
              FROM resolver_features
            )
            DELETE FROM resolver_features rf
            USING ranked r
            WHERE rf.ctid = r.ctid AND r.rn > 1;

            -- created_at
            EXECUTE 'ALTER TABLE resolver_features ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()';
            EXECUTE 'UPDATE resolver_features SET created_at = COALESCE(created_at, now())';

            -- unique(run_id, nct_id, company_id)
            IF NOT EXISTS (
              SELECT 1 FROM pg_constraint WHERE conname = 'resolver_features_run_nct_cid_key'
            ) THEN
              EXECUTE 'ALTER TABLE resolver_features
                       ADD CONSTRAINT resolver_features_run_nct_cid_key
                       UNIQUE (run_id, nct_id, company_id)';
            END IF;

            -- indexes
            EXECUTE 'CREATE INDEX IF NOT EXISTS resolver_features_nct_idx ON resolver_features (nct_id)';
            EXECUTE 'CREATE INDEX IF NOT EXISTS resolver_features_run_idx ON resolver_features (run_id)';
            EXECUTE 'CREATE INDEX IF NOT EXISTS resolver_features_cid_idx ON resolver_features (company_id)';
          END IF;
        END
        $$;
        """
    )

    # --- resolver_decisions hardening (these tables exist in earlier revs) ---
    # Add/ensure columns on resolver_decisions (safe if already present)
    op.execute(
        """
        ALTER TABLE IF EXISTS resolver_decisions
          ADD COLUMN IF NOT EXISTS sponsor_text_norm TEXT,
          ADD COLUMN IF NOT EXISTS p_match NUMERIC,
          ADD COLUMN IF NOT EXISTS top2_margin NUMERIC,
          ADD COLUMN IF NOT EXISTS decided_by TEXT DEFAULT 'auto',
          ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ DEFAULT now()
        """
    )

    # Unique (run_id, nct_id, sponsor_text_norm)
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.resolver_decisions') IS NOT NULL THEN
            IF NOT EXISTS (
              SELECT 1 FROM pg_constraint WHERE conname = 'resolver_decisions_run_nct_snorm_key'
            ) THEN
              EXECUTE 'ALTER TABLE resolver_decisions
                       ADD CONSTRAINT resolver_decisions_run_nct_snorm_key
                       UNIQUE (run_id, nct_id, sponsor_text_norm)';
            END IF;
          END IF;
        END
        $$;
        """
    )


def downgrade():
    # Drop helper indexes on resolver_features (only if table exists)
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.resolver_features') IS NOT NULL THEN
            EXECUTE 'DROP INDEX IF EXISTS resolver_features_cid_idx';
            EXECUTE 'DROP INDEX IF EXISTS resolver_features_run_idx';
            EXECUTE 'DROP INDEX IF EXISTS resolver_features_nct_idx';
            IF EXISTS (
              SELECT 1 FROM pg_constraint WHERE conname = 'resolver_features_run_nct_cid_key'
            ) THEN
              EXECUTE 'ALTER TABLE resolver_features DROP CONSTRAINT resolver_features_run_nct_cid_key';
            END IF;
          END IF;
        END
        $$;
        """
    )

    # Remove the decisions unique if present
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.resolver_decisions') IS NOT NULL THEN
            IF EXISTS (
              SELECT 1 FROM pg_constraint WHERE conname = 'resolver_decisions_run_nct_snorm_key'
            ) THEN
              EXECUTE 'ALTER TABLE resolver_decisions DROP CONSTRAINT resolver_decisions_run_nct_snorm_key';
            END IF;
          END IF;
        END
        $$;
        """
    )
