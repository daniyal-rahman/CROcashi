"""Create studies table and pivotal study guardrails (idempotent)

Revision ID: 20250121_create_studies_table_and_guardrails
Revises: 20250121_add_how_to_study_assets_xref
Create Date: 2025-01-21 16:00:00.000000
"""
from typing import Sequence, Union, Optional

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision: str = "20250121_create_studies_table_and_guardrails"
down_revision: Union[str, Sequence[str], None] = "20250121_add_how_to_study_assets_xref"
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
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name=:c
            """,
            t=table, c=col,
        )
    )

def _col_udt_name(table: str, col: str) -> Optional[str]:
    return _scalar(
        """
        SELECT udt_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:t AND column_name=:c
        """,
        t=table, c=col,
    )

def _fk_exists(conname: str) -> bool:
    return _constraint_exists(conname)

def _trigger_exists(table: str, trig: str) -> bool:
    return bool(
        _scalar(
            """
            SELECT 1
            FROM pg_trigger
            WHERE NOT tgisinternal AND tgname=:trig
              AND tgrelid = (SELECT oid FROM pg_class WHERE relname=:tbl AND relnamespace = 'public'::regnamespace)
            LIMIT 1
            """,
            trig=trig, tbl=table,
        )
    )


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # studies (ensure exists; ensure extracted_jsonb is JSONB)
    # -------------------------------------------------------------------------
    if not _table_exists("studies"):
        op.create_table(
            "studies",
            sa.Column("study_id", sa.BigInteger(), nullable=False),
            sa.Column("trial_id", sa.BigInteger(), nullable=False),
            sa.Column("doc_type", sa.Text(), nullable=False),
            sa.Column("citation", sa.Text(), nullable=True),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("url", sa.Text(), nullable=True),
            sa.Column("oa_status", sa.Text(), nullable=False, server_default=sa.text("'unknown'")),
            sa.Column("extracted_jsonb", psql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("coverage_level", sa.Text(), nullable=True),
            sa.Column("notes_md", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["trial_id"], ["trials.trial_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("study_id"),
        )
    else:
        # If column exists but is JSON (not JSONB), convert it.
        if _col_exists("studies", "extracted_jsonb"):
            udt = _col_udt_name("studies", "extracted_jsonb")
            if udt == "json":
                op.execute(
                    "ALTER TABLE public.studies "
                    "ALTER COLUMN extracted_jsonb TYPE jsonb USING extracted_jsonb::jsonb;"
                )
        else:
            # Add column if missing
            op.add_column("studies", sa.Column("extracted_jsonb", psql.JSONB(astext_type=sa.Text()), nullable=True))

    # Indexes on studies
    if not _idx_exists("ix_studies_trial"):
        op.create_index("ix_studies_trial", "studies", ["trial_id"])
    if not _idx_exists("ix_studies_coverage"):
        op.create_index("ix_studies_coverage", "studies", ["coverage_level"])
    if not _idx_exists("ix_studies_year"):
        op.create_index("ix_studies_year", "studies", ["year"])
    if not _idx_exists("ix_studies_doc_type"):
        op.create_index("ix_studies_doc_type", "studies", ["doc_type"])

    # JSONB GIN index (avoid jsonb_path_ops vs json mismatch by indexing JSONB with default opclass)
    if not _idx_exists("idx_studies_extracted_jsonb"):
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_studies_extracted_jsonb
              ON public.studies USING gin (extracted_jsonb);
            """
        )

    # -------------------------------------------------------------------------
    # document_links: add study_id + FK + index (idempotent)
    # -------------------------------------------------------------------------
    if _table_exists("document_links"):
        if not _col_exists("document_links", "study_id"):
            op.add_column("document_links", sa.Column("study_id", sa.BigInteger(), nullable=True))
        if not _fk_exists("fk_document_links_study_id"):
            op.create_foreign_key(
                "fk_document_links_study_id",
                "document_links",
                "studies",
                ["study_id"],
                ["study_id"],
                ondelete="SET NULL",
            )
        if not _idx_exists("ix_doclinks_study"):
            op.create_index("ix_doclinks_study", "document_links", ["study_id"])

    # -------------------------------------------------------------------------
    # Guardrails function + trigger (idempotent)
    # -------------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_pivotal_study_card()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
          is_piv bool;
          card jsonb;
          total_n int;
          primary_count int;
          has_effect_or_p bool := false;
        BEGIN
          SELECT is_pivotal INTO is_piv FROM trials WHERE trial_id = NEW.trial_id;
          IF NOT is_piv THEN RETURN NEW; END IF;

          card := NEW.extracted_jsonb;
          IF card IS NULL THEN RETURN NEW; END IF;

          SELECT COALESCE(jsonb_array_length(card->'primary_endpoints'),0)
          INTO primary_count;
          IF primary_count = 0 THEN
            RAISE EXCEPTION 'PivotalStudyMissingFields: primary_endpoints';
          END IF;

          total_n := (card #>> '{sample_size,total_n}')::int;
          IF total_n IS NULL THEN
            RAISE EXCEPTION 'PivotalStudyMissingFields: sample_size.total_n';
          END IF;

          IF card #>> '{populations,analysis_primary_on}' IS NULL THEN
            RAISE EXCEPTION 'PivotalStudyMissingFields: populations.analysis_primary_on';
          END IF;

          has_effect_or_p := EXISTS (
            SELECT 1
            FROM jsonb_array_elements(card->'results'->'primary') AS it(item)
            WHERE (it.item #>> '{effect_size,value}') IS NOT NULL
               OR (it.item #>> '{p_value}') IS NOT NULL
          );
          IF NOT has_effect_or_p THEN
            RAISE EXCEPTION 'PivotalStudyMissingFields: results.primary.(effect_size.value OR p_value)';
          END IF;

          RETURN NEW;
        END $$;
        """
    )

    # Recreate trigger cleanly
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_pivotal_study_card ON public.studies;")
    op.execute(
        """
        CREATE TRIGGER trg_enforce_pivotal_study_card
          BEFORE INSERT OR UPDATE OF extracted_jsonb ON public.studies
          FOR EACH ROW
          EXECUTE FUNCTION enforce_pivotal_study_card();
        """
    )


def downgrade() -> None:
    # Drop trigger and function (idempotent)
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_pivotal_study_card ON public.studies;")
    op.execute("DROP FUNCTION IF EXISTS enforce_pivotal_study_card();")

    # Drop index on studies.extracted_jsonb
    if _idx_exists("idx_studies_extracted_jsonb"):
        op.execute("DROP INDEX IF EXISTS idx_studies_extracted_jsonb;")

    # document_links cleanup
    if _table_exists("document_links"):
        if _idx_exists("ix_doclinks_study"):
            op.drop_index("ix_doclinks_study", table_name="document_links")
        if _fk_exists("fk_document_links_study_id"):
            op.drop_constraint("fk_document_links_study_id", "document_links", type_="foreignkey")
        if _col_exists("document_links", "study_id"):
            op.drop_column("document_links", "study_id")

    # studies indexes + table
    for idx in ("ix_studies_doc_type", "ix_studies_year", "ix_studies_coverage", "ix_studies_trial"):
        if _idx_exists(idx):
            op.drop_index(idx, table_name="studies")
    if _table_exists("studies"):
        op.drop_table("studies")
