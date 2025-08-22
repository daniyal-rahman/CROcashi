"""Create document staging tables and assets model (idempotent)

Revision ID: 20250121_create_document_staging_and_assets
Revises: aa81babe6641
Create Date: 2025-01-21 10:00:00.000000
"""
from typing import Sequence, Union, Optional

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision: str = "20250121_create_document_staging_and_assets"
down_revision: Union[str, Sequence[str], None] = "aa81babe6641"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------- helpers ----------
def _regclass(name: str) -> Optional[str]:
    bind = op.get_bind()
    return bind.execute(sa.text("SELECT to_regclass(:t)"), {"t": f"public.{name}"}).scalar()

def _table_exists(name: str) -> bool:
    return _regclass(name) is not None

def _idx_exists(idx: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:i LIMIT 1"
            ),
            {"i": idx},
        ).scalar()
    )

def _constraint_exists(conname: str) -> bool:
    bind = op.get_bind()
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname=:c LIMIT 1"),
            {"c": conname},
        ).scalar()
    )


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # Pre-create enums idempotently so CREATE TYPE doesn't collide
    # -------------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'doc_source_type') THEN
            CREATE TYPE doc_source_type AS ENUM ('PR','IR','Abstract','Paper','Registry','FDA','SEC_8K','Other');
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'doc_status') THEN
            CREATE TYPE doc_status AS ENUM ('discovered','fetched','parsed','indexed','linked','ready_for_card','card_built','error');
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'oa_status') THEN
            CREATE TYPE oa_status AS ENUM ('open','green','bronze','closed','unknown');
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'asset_alias_type') THEN
            CREATE TYPE asset_alias_type AS ENUM ('inn','generic','brand','code','chembl','drugbank','unii','cas','inchikey','other');
          END IF;
        END$$;
        """
    )

    # Bind ENUM objects with create_type=False so SQLAlchemy doesn't try to CREATE TYPE again
    doc_source_enum = psql.ENUM(
        "PR", "IR", "Abstract", "Paper", "Registry", "FDA", "SEC_8K", "Other",
        name="doc_source_type", create_type=False
    )
    doc_status_enum = psql.ENUM(
        "discovered", "fetched", "parsed", "indexed", "linked",
        "ready_for_card", "card_built", "error",
        name="doc_status", create_type=False
    )
    oa_status_enum = psql.ENUM(
        "open", "green", "bronze", "closed", "unknown",
        name="oa_status", create_type=False
    )
    asset_alias_enum = psql.ENUM(
        "inn", "generic", "brand", "code", "chembl", "drugbank",
        "unii", "cas", "inchikey", "other",
        name="asset_alias_type", create_type=False
    )

    # -------------------------------------------------------------------------
    # assets
    # -------------------------------------------------------------------------
    if not _table_exists("assets"):
        op.create_table(
            "assets",
            sa.Column("asset_id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("names_jsonb", psql.JSONB(astext_type=sa.Text()), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("modality", sa.Text()),
            sa.Column("target", sa.Text()),
            sa.Column("moa", sa.Text()),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

    # -------------------------------------------------------------------------
    # asset_aliases
    # -------------------------------------------------------------------------
    if not _table_exists("asset_aliases"):
        op.create_table(
            "asset_aliases",
            sa.Column("asset_alias_id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.BigInteger(), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
            sa.Column("alias", sa.Text(), nullable=False),
            sa.Column("alias_norm", sa.Text(), nullable=False),
            sa.Column("alias_type", asset_alias_enum, nullable=False),
            sa.Column("source", sa.Text()),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
    if not _constraint_exists("uq_asset_alias_norm_type"):
        op.create_unique_constraint(
            "uq_asset_alias_norm_type", "asset_aliases", ["asset_id", "alias_norm", "alias_type"]
        )
    if not _idx_exists("ix_asset_alias_norm"):
        op.create_index("ix_asset_alias_norm", "asset_aliases", ["alias_norm"])

    # -------------------------------------------------------------------------
    # documents
    # -------------------------------------------------------------------------
    if not _table_exists("documents"):
        op.create_table(
            "documents",
            sa.Column("doc_id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("source_type", doc_source_enum, nullable=False),
            sa.Column("source_url", sa.Text(), unique=True),
            sa.Column("publisher", sa.Text()),
            sa.Column("published_at", sa.TIMESTAMP(timezone=True)),
            sa.Column("storage_uri", sa.Text(), nullable=False),
            sa.Column("content_type", sa.Text()),
            sa.Column("sha256", sa.Text(), nullable=False),
            sa.Column("oa_status", oa_status_enum, server_default=sa.text("'unknown'::oa_status")),
            sa.Column("discovered_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("fetched_at", sa.TIMESTAMP(timezone=True)),
            sa.Column("parsed_at", sa.TIMESTAMP(timezone=True)),
            sa.Column("status", doc_status_enum, server_default=sa.text("'discovered'::doc_status"), nullable=False),
            sa.Column("error_msg", sa.Text()),
            sa.Column("crawl_run_id", sa.Text()),
        )
    if not _idx_exists("ix_documents_sha256"):
        op.create_index("ix_documents_sha256", "documents", ["sha256"])
    if not _idx_exists("ix_documents_published_at"):
        op.create_index("ix_documents_published_at", "documents", ["published_at"])
    if not _idx_exists("ix_documents_status"):
        op.create_index("ix_documents_status", "documents", ["status"])
    if not _idx_exists("ix_documents_type_date"):
        op.create_index("ix_documents_type_date", "documents", ["source_type", "published_at"])

    # -------------------------------------------------------------------------
    # document_text_pages
    # -------------------------------------------------------------------------
    if not _table_exists("document_text_pages"):
        op.create_table(
            "document_text_pages",
            sa.Column("doc_id", sa.BigInteger(), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
            sa.Column("page_no", sa.Integer(), nullable=False),
            sa.Column("char_count", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("doc_id", "page_no"),
        )

    # -------------------------------------------------------------------------
    # document_tables
    # -------------------------------------------------------------------------
    if not _table_exists("document_tables"):
        op.create_table(
            "document_tables",
            sa.Column("doc_id", sa.BigInteger(), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
            sa.Column("page_no", sa.Integer(), nullable=False),
            sa.Column("table_idx", sa.Integer(), nullable=False),
            sa.Column("table_jsonb", psql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("detector", sa.Text()),
            sa.PrimaryKeyConstraint("doc_id", "page_no", "table_idx"),
        )

    # -------------------------------------------------------------------------
    # document_links
    # -------------------------------------------------------------------------
    if not _table_exists("document_links"):
        op.create_table(
            "document_links",
            sa.Column("doc_id", sa.BigInteger(), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
            sa.Column("nct_id", sa.Text()),
            sa.Column("asset_id", sa.BigInteger(), sa.ForeignKey("assets.asset_id", ondelete="SET NULL")),
            sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.company_id", ondelete="SET NULL")),
            sa.Column("link_type", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
    if not _idx_exists("ix_doclinks_doc"):
        op.create_index("ix_doclinks_doc", "document_links", ["doc_id"])
    if not _idx_exists("ix_doclinks_asset"):
        op.create_index("ix_doclinks_asset", "document_links", ["asset_id"])
    if not _idx_exists("ix_doclinks_nct"):
        op.create_index("ix_doclinks_nct", "document_links", ["nct_id"])
    if not _constraint_exists("ck_doclinks_confidence"):
        op.create_check_constraint(
            "ck_doclinks_confidence", "document_links", "confidence >= 0 AND confidence <= 1"
        )

    # -------------------------------------------------------------------------
    # document_entities
    # -------------------------------------------------------------------------
    if not _table_exists("document_entities"):
        op.create_table(
            "document_entities",
            sa.Column("doc_id", sa.BigInteger(), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
            sa.Column(
                "ent_type",
                sa.Text(),
                nullable=False,
                # examples: 'endpoint','n_total','p_value','effect_size','population','subgroup','code','inn','generic'
            ),
            sa.Column("value_text", sa.Text(), nullable=False),
            sa.Column("value_norm", sa.Text()),
            sa.Column("page_no", sa.Integer()),
            sa.Column("char_start", sa.Integer()),
            sa.Column("char_end", sa.Integer()),
            sa.Column("detector", sa.Text()),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
    if not _idx_exists("ix_docents_doc"):
        op.create_index("ix_docents_doc", "document_entities", ["doc_id"])
    if not _idx_exists("ix_docents_type"):
        op.create_index("ix_docents_type", "document_entities", ["ent_type"])

    # -------------------------------------------------------------------------
    # document_citations
    # -------------------------------------------------------------------------
    if not _table_exists("document_citations"):
        op.create_table(
            "document_citations",
            sa.Column("doc_id", sa.BigInteger(), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
            sa.Column("doi", sa.Text()),
            sa.Column("pmid", sa.Text()),
            sa.Column("pmcid", sa.Text()),
            sa.Column("crossref_jsonb", psql.JSONB(astext_type=sa.Text())),
            sa.Column("unpaywall_jsonb", psql.JSONB(astext_type=sa.Text())),
            sa.PrimaryKeyConstraint("doc_id"),
        )

    # -------------------------------------------------------------------------
    # document_notes
    # -------------------------------------------------------------------------
    if not _table_exists("document_notes"):
        op.create_table(
            "document_notes",
            sa.Column("doc_id", sa.BigInteger(), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
            sa.Column("notes_md", sa.Text()),
            sa.Column("author", sa.Text()),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("doc_id"),
        )


def downgrade() -> None:
    # Drop tables in reverse dependency order (idempotent)
    if _table_exists("document_notes"):
        op.drop_table("document_notes")
    if _table_exists("document_citations"):
        op.drop_table("document_citations")
    if _idx_exists("ix_docents_type"):
        op.drop_index("ix_docents_type", table_name="document_entities")
    if _idx_exists("ix_docents_doc"):
        op.drop_index("ix_docents_doc", table_name="document_entities")
    if _table_exists("document_entities"):
        op.drop_table("document_entities")

    if _constraint_exists("ck_doclinks_confidence"):
        op.drop_check_constraint("ck_doclinks_confidence", "document_links")
    if _idx_exists("ix_doclinks_nct"):
        op.drop_index("ix_doclinks_nct", table_name="document_links")
    if _idx_exists("ix_doclinks_asset"):
        op.drop_index("ix_doclinks_asset", table_name="document_links")
    if _idx_exists("ix_doclinks_doc"):
        op.drop_index("ix_doclinks_doc", table_name="document_links")
    if _table_exists("document_links"):
        op.drop_table("document_links")

    if _table_exists("document_tables"):
        op.drop_table("document_tables")
    if _table_exists("document_text_pages"):
        op.drop_table("document_text_pages")

    if _idx_exists("ix_documents_type_date"):
        op.drop_index("ix_documents_type_date", table_name="documents")
    if _idx_exists("ix_documents_status"):
        op.drop_index("ix_documents_status", table_name="documents")
    if _idx_exists("ix_documents_published_at"):
        op.drop_index("ix_documents_published_at", table_name="documents")
    if _idx_exists("ix_documents_sha256"):
        op.drop_index("ix_documents_sha256", table_name="documents")
    if _table_exists("documents"):
        op.drop_table("documents")

    if _idx_exists("ix_asset_alias_norm"):
        op.drop_index("ix_asset_alias_norm", table_name="asset_aliases")
    if _constraint_exists("uq_asset_alias_norm_type"):
        op.drop_constraint("uq_asset_alias_norm_type", "asset_aliases", type_="unique")
    if _table_exists("asset_aliases"):
        op.drop_table("asset_aliases")
    if _table_exists("assets"):
        op.drop_table("assets")

    # Drop enums (only after all dependent columns are gone)
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_attribute a
            JOIN pg_type t ON a.atttypid = t.oid
            WHERE t.typname IN ('asset_alias_type','oa_status','doc_status','doc_source_type')
              AND a.attnum > 0 AND NOT a.attisdropped
          ) THEN
            DROP TYPE IF EXISTS asset_alias_type;
            DROP TYPE IF EXISTS oa_status;
            DROP TYPE IF EXISTS doc_status;
            DROP TYPE IF EXISTS doc_source_type;
          END IF;
        END$$;
        """
    )
