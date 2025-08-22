"""Create final xref tables for promoted asset links (idempotent)

Revision ID: 20250121_create_final_xref_tables
Revises: 20250121_create_document_staging_and_assets
Create Date: 2025-01-21 12:00:00.000000
"""
from typing import Sequence, Union, Optional

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision: str = "20250121_create_final_xref_tables"
down_revision: Union[str, Sequence[str], None] = "20250121_create_document_staging_and_assets"
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
    # study_assets_xref
    # -------------------------------------------------------------------------
    if not _table_exists("study_assets_xref"):
        op.create_table(
            "study_assets_xref",
            sa.Column("xref_id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("study_id", sa.Text(), nullable=False),  # NCT or other study identifier
            sa.Column("asset_id", sa.BigInteger(), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
            sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
            sa.Column("evidence_jsonb", psql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("link_source", sa.Text(), nullable=False),  # 'document_link', 'manual', etc.
            sa.Column("source_doc_id", sa.BigInteger(), sa.ForeignKey("documents.doc_id", ondelete="SET NULL")),
            sa.Column("promoted_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("promoted_by", sa.Text()),  # 'auto', 'manual', 'system'
            sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),  # 'active','inactive','review'
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

    if not _idx_exists("ix_study_assets_xref_study"):
        op.create_index("ix_study_assets_xref_study", "study_assets_xref", ["study_id"])
    if not _idx_exists("ix_study_assets_xref_asset"):
        op.create_index("ix_study_assets_xref_asset", "study_assets_xref", ["asset_id"])
    if not _idx_exists("ix_study_assets_xref_confidence"):
        op.create_index("ix_study_assets_xref_confidence", "study_assets_xref", ["confidence"])
    if not _idx_exists("ix_study_assets_xref_status"):
        op.create_index("ix_study_assets_xref_status", "study_assets_xref", ["status"])
    if not _constraint_exists("ck_study_assets_confidence"):
        op.create_check_constraint(
            "ck_study_assets_confidence", "study_assets_xref", "confidence >= 0 AND confidence <= 1"
        )
    if not _constraint_exists("uq_study_assets_study_asset"):
        op.create_unique_constraint(
            "uq_study_assets_study_asset", "study_assets_xref", ["study_id", "asset_id"]
        )

    # -------------------------------------------------------------------------
    # trial_assets_xref
    # -------------------------------------------------------------------------
    if not _table_exists("trial_assets_xref"):
        op.create_table(
            "trial_assets_xref",
            sa.Column("xref_id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("nct_id", sa.Text(), nullable=False),  # ClinicalTrials.gov identifier
            sa.Column("asset_id", sa.BigInteger(), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
            sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
            sa.Column("evidence_jsonb", psql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("link_source", sa.Text(), nullable=False),  # 'document_link','ctgov','manual', etc.
            sa.Column("source_doc_id", sa.BigInteger(), sa.ForeignKey("documents.doc_id", ondelete="SET NULL")),
            sa.Column("promoted_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("promoted_by", sa.Text()),
            sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),  # 'active','inactive','review'
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

    if not _idx_exists("ix_trial_assets_xref_nct"):
        op.create_index("ix_trial_assets_xref_nct", "trial_assets_xref", ["nct_id"])
    if not _idx_exists("ix_trial_assets_xref_asset"):
        op.create_index("ix_trial_assets_xref_asset", "trial_assets_xref", ["asset_id"])
    if not _idx_exists("ix_trial_assets_xref_confidence"):
        op.create_index("ix_trial_assets_xref_confidence", "trial_assets_xref", ["confidence"])
    if not _idx_exists("ix_trial_assets_xref_status"):
        op.create_index("ix_trial_assets_xref_status", "trial_assets_xref", ["status"])
    if not _constraint_exists("ck_trial_assets_confidence"):
        op.create_check_constraint(
            "ck_trial_assets_confidence", "trial_assets_xref", "confidence >= 0 AND confidence <= 1"
        )
    if not _constraint_exists("uq_trial_assets_nct_asset"):
        op.create_unique_constraint(
            "uq_trial_assets_nct_asset", "trial_assets_xref", ["nct_id", "asset_id"]
        )

    # -------------------------------------------------------------------------
    # link_audit
    # -------------------------------------------------------------------------
    if not _table_exists("link_audit"):
        op.create_table(
            "link_audit",
            sa.Column("audit_id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("doc_id", sa.BigInteger(), sa.ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False),
            sa.Column("asset_id", sa.BigInteger(), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
            sa.Column("nct_id", sa.Text()),
            sa.Column("link_type", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
            sa.Column("heuristic_applied", sa.Text()),  # 'HP-1', 'HP-2', ...
            sa.Column("evidence_jsonb", psql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("promotion_status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),  # 'pending','promoted','rejected','review'
            sa.Column("review_notes", sa.Text()),
            sa.Column("reviewed_by", sa.Text()),
            sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True)),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

    if not _idx_exists("ix_link_audit_doc"):
        op.create_index("ix_link_audit_doc", "link_audit", ["doc_id"])
    if not _idx_exists("ix_link_audit_asset"):
        op.create_index("ix_link_audit_asset", "link_audit", ["asset_id"])
    if not _idx_exists("ix_link_audit_nct"):
        op.create_index("ix_link_audit_nct", "link_audit", ["nct_id"])
    if not _idx_exists("ix_link_audit_confidence"):
        op.create_index("ix_link_audit_confidence", "link_audit", ["confidence"])
    if not _idx_exists("ix_link_audit_promotion_status"):
        op.create_index("ix_link_audit_promotion_status", "link_audit", ["promotion_status"])
    if not _idx_exists("ix_link_audit_heuristic"):
        op.create_index("ix_link_audit_heuristic", "link_audit", ["heuristic_applied"])
    if not _constraint_exists("ck_link_audit_confidence"):
        op.create_check_constraint(
            "ck_link_audit_confidence", "link_audit", "confidence >= 0 AND confidence <= 1"
        )

    # -------------------------------------------------------------------------
    # merge_candidates
    # -------------------------------------------------------------------------
    if not _table_exists("merge_candidates"):
        op.create_table(
            "merge_candidates",
            sa.Column("merge_id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("asset_id_1", sa.BigInteger(), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
            sa.Column("asset_id_2", sa.BigInteger(), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), nullable=False),
            sa.Column("merge_reason", sa.Text(), nullable=False),  # 'same_inchikey','same_unii','same_chembl','explicit_equivalence'
            sa.Column("evidence_jsonb", psql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
            sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),  # 'pending','approved','rejected','merged'
            sa.Column("reviewed_by", sa.Text()),
            sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True)),
            sa.Column("review_notes", sa.Text()),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

    if not _idx_exists("ix_merge_candidates_asset1"):
        op.create_index("ix_merge_candidates_asset1", "merge_candidates", ["asset_id_1"])
    if not _idx_exists("ix_merge_candidates_asset2"):
        op.create_index("ix_merge_candidates_asset2", "merge_candidates", ["asset_id_2"])
    if not _idx_exists("ix_merge_candidates_status"):
        op.create_index("ix_merge_candidates_status", "merge_candidates", ["status"])
    if not _constraint_exists("ck_merge_candidates_different"):
        op.create_check_constraint(
            "ck_merge_candidates_different", "merge_candidates", "asset_id_1 != asset_id_2"
        )


def downgrade() -> None:
    # Drop tables in reverse order (idempotent)
    if _table_exists("merge_candidates"):
        op.drop_table("merge_candidates")
    if _table_exists("link_audit"):
        op.drop_table("link_audit")
    if _table_exists("trial_assets_xref"):
        op.drop_table("trial_assets_xref")
    if _table_exists("study_assets_xref"):
        op.drop_table("study_assets_xref")
