"""Fix TrialAssetsXref to use trial_id instead of nct_id (idempotent)

Revision ID: 20250121_fix_trial_assets_xref_trial_id
Revises: 20250121_add_confidence_to_document_entity
Create Date: 2025-01-21 15:00:00.000000
"""
from typing import Sequence, Union, Optional

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20250121_fix_trial_assets_xref_trial_id"
down_revision: Union[str, Sequence[str], None] = "20250121_add_confidence_to_document_entity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------- helpers ----------
def _scalar(sql: str, **params):
    bind = op.get_bind()
    return bind.execute(sa.text(sql), params).scalar()

def _regclass(name: str) -> Optional[str]:
    return _scalar("SELECT to_regclass(:t)", t=f"public.{name}")

def _table_exists(name: str) -> bool:
    return _regclass(name) is not None

def _idx_exists(idx: str) -> bool:
    return bool(_scalar("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:i LIMIT 1", i=idx))

def _constraint_exists(conname: str) -> bool:
    return bool(_scalar("SELECT 1 FROM pg_constraint WHERE conname=:c LIMIT 1", c=conname))

def _col_exists(table: str, col: str) -> bool:
    return bool(
        _scalar(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t AND column_name=:c",
            t=table, c=col,
        )
    )

def _col_nullable(table: str, col: str) -> Optional[bool]:
    val = _scalar(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c",
        t=table, c=col,
    )
    if val is None:
        return None
    return val == "YES"


def upgrade() -> None:
    # Only proceed if the table exists (created in 20250121_create_final_xref_tables)
    if not _table_exists("trial_assets_xref"):
        return

    # 1) Drop old UNIQUE/INDEX on nct_id if they exist
    if _constraint_exists("uq_trial_assets_nct_asset"):
        op.drop_constraint("uq_trial_assets_nct_asset", "trial_assets_xref", type_="unique")
    if _idx_exists("ix_trial_assets_xref_nct"):
        op.drop_index("ix_trial_assets_xref_nct", table_name="trial_assets_xref")

    # 2) Add trial_id column (nullable for backfill), if missing
    if not _col_exists("trial_assets_xref", "trial_id"):
        op.execute(
            """
            ALTER TABLE public.trial_assets_xref
            ADD COLUMN IF NOT EXISTS trial_id bigint;
            """
        )

    # 3) Create FK to trials(trial_id) if missing (only if trials exists)
    if _table_exists("trials") and not _constraint_exists("fk_trial_assets_xref_trial_id"):
        op.create_foreign_key(
            "fk_trial_assets_xref_trial_id",
            "trial_assets_xref",
            "trials",
            ["trial_id"],
            ["trial_id"],
            ondelete="CASCADE",
        )

    # 4) Backfill trial_id from nct_id via trials.nct_id if available
    if _col_exists("trial_assets_xref", "trial_id") and _col_exists("trial_assets_xref", "nct_id") and _col_exists("trials", "nct_id"):
        op.execute(
            """
            UPDATE public.trial_assets_xref t
            SET trial_id = tr.trial_id
            FROM public.trials tr
            WHERE t.trial_id IS NULL
              AND t.nct_id IS NOT NULL
              AND tr.nct_id = t.nct_id;
            """
        )

    # 5) Add how column, backfill, and set NOT NULL (idempotent)
    if not _col_exists("trial_assets_xref", "how"):
        op.execute(
            "ALTER TABLE public.trial_assets_xref ADD COLUMN how text;"
        )
    # Backfill NULLs
    op.execute("UPDATE public.trial_assets_xref SET how = 'legacy_migration' WHERE how IS NULL;")
    # Set NOT NULL if still nullable and no NULLs remain
    if _col_nullable("trial_assets_xref", "how") is True:
        op.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM public.trial_assets_xref WHERE how IS NULL) THEN
                ALTER TABLE public.trial_assets_xref ALTER COLUMN how SET NOT NULL;
              END IF;
            END$$;
            """
        )

    # 6) Create new UNIQUE(trial_id, asset_id) and index on trial_id
    if not _constraint_exists("uq_trial_assets_trial_asset"):
        op.create_unique_constraint(
            "uq_trial_assets_trial_asset", "trial_assets_xref", ["trial_id", "asset_id"]
        )
    if not _idx_exists("ix_trial_assets_xref_trial"):
        op.create_index("ix_trial_assets_xref_trial", "trial_assets_xref", ["trial_id"])

    # 7) Make trial_id NOT NULL once backfilled
    if _col_nullable("trial_assets_xref", "trial_id") is True:
        op.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM public.trial_assets_xref WHERE trial_id IS NULL) THEN
                ALTER TABLE public.trial_assets_xref ALTER COLUMN trial_id SET NOT NULL;
              END IF;
            END$$;
            """
        )

    # 8) Finally, drop nct_id column if it still exists
    if _col_exists("trial_assets_xref", "nct_id"):
        op.execute("ALTER TABLE public.trial_assets_xref DROP COLUMN IF EXISTS nct_id;")


def downgrade() -> None:
    # Only proceed if the table exists
    if not _table_exists("trial_assets_xref"):
        return

    # 1) Drop new index/unique on trial_id
    if _idx_exists("ix_trial_assets_xref_trial"):
        op.drop_index("ix_trial_assets_xref_trial", table_name="trial_assets_xref")
    if _constraint_exists("uq_trial_assets_trial_asset"):
        op.drop_constraint("uq_trial_assets_trial_asset", "trial_assets_xref", type_="unique")

    # 2) Recreate nct_id column if missing
    if not _col_exists("trial_assets_xref", "nct_id"):
        op.execute("ALTER TABLE public.trial_assets_xref ADD COLUMN nct_id text;")

    # 3) Backfill nct_id from trials if possible
    if _col_exists("trial_assets_xref", "trial_id") and _col_exists("trials", "nct_id"):
        op.execute(
            """
            UPDATE public.trial_assets_xref t
            SET nct_id = tr.nct_id
            FROM public.trials tr
            WHERE t.nct_id IS NULL
              AND t.trial_id IS NOT NULL
              AND tr.trial_id = t.trial_id;
            """
        )

    # 4) Recreate old UNIQUE/INDEX on nct_id
    if not _constraint_exists("uq_trial_assets_nct_asset"):
        op.create_unique_constraint(
            "uq_trial_assets_nct_asset", "trial_assets_xref", ["nct_id", "asset_id"]
        )
    if not _idx_exists("ix_trial_assets_xref_nct"):
        op.create_index("ix_trial_assets_xref_nct", "trial_assets_xref", ["nct_id"])

    # 5) Drop how column if present
    if _col_exists("trial_assets_xref", "how"):
        op.execute("ALTER TABLE public.trial_assets_xref DROP COLUMN IF EXISTS how;")

    # 6) Drop FK and trial_id column (in this order)
    if _constraint_exists("fk_trial_assets_xref_trial_id"):
        op.drop_constraint("fk_trial_assets_xref_trial_id", "trial_assets_xref", type_="foreignkey")
    if _col_exists("trial_assets_xref", "trial_id"):
        op.execute("ALTER TABLE public.trial_assets_xref DROP COLUMN IF EXISTS trial_id;")
