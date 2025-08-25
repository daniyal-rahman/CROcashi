"""Studies and Disclosures

Revision ID: 34689bd20f02
Revises: cc44d2e61b7e
Create Date: 2025-08-24 21:34:42.644179

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '34689bd20f02'
down_revision: Union[str, Sequence[str], None] = 'cc44d2e61b7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from sqlalchemy.dialects import postgresql as psql

DOC_TYPES = ("PR", "8K", "Abstract", "Poster", "Paper", "Registry", "FDA")
OA_STATUSES = ("oa_gold", "oa_green", "accepted_ms", "embargoed", "unknown")
COVERAGE_LEVELS = ("high", "med", "low")


def upgrade() -> None:
    # -------------------
    # studies
    # -------------------
    op.create_table(
        "studies",
        sa.Column("study_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("trial_id", sa.Integer, sa.ForeignKey("trials.trial_id", name="fk_studies_trials", ondelete="CASCADE"), nullable=True),
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.asset_id", name="fk_studies_assets", ondelete="SET NULL"), nullable=True),
        sa.Column("doc_type", sa.String(length=16), nullable=False),
        sa.Column("citation", sa.Text, nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("hash", sa.String(length=64), nullable=True),
        sa.Column("oa_status", sa.String(length=16), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("object_store_key", sa.Text, nullable=True),
        sa.Column("extracted_jsonb", psql.JSONB, nullable=True),
        sa.Column("coverage_level", sa.String(length=8), nullable=True),
        sa.Column("notes_md", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("study_id", name="pk_studies"),
    )
    # CHECK constraints (embed literals)
    doc_list = ", ".join(f"'{v}'" for v in DOC_TYPES)
    oa_list = ", ".join(f"'{v}'" for v in OA_STATUSES)
    cov_list = ", ".join(f"'{v}'" for v in COVERAGE_LEVELS)
    op.create_check_constraint("ck_studies_doc_type", "studies", f"(doc_type IN ({doc_list}))")
    op.create_check_constraint("ck_studies_oa_status", "studies", f"(oa_status IN ({oa_list}))")
    op.create_check_constraint("ck_studies_coverage_level", "studies", f"(coverage_level IS NULL OR coverage_level IN ({cov_list}))")

    # Indexes for studies
    op.create_index("idx_studies_trial", "studies", ["trial_id"])
    op.create_index("idx_studies_asset", "studies", ["asset_id"])
    op.create_index("idx_studies_extracted_jsonb", "studies", ["extracted_jsonb"], postgresql_using="gin")
    # Partial unique on hash when not null
    op.create_index(
        "uq_studies_hash_notnull",
        "studies",
        ["hash"],
        unique=True,
        postgresql_where=sa.text("hash IS NOT NULL"),
    )

    # -------------------
    # disclosures (kept separate)
    # -------------------
    op.create_table(
        "disclosures",
        sa.Column("disclosure_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("trial_id", sa.Integer, sa.ForeignKey("trials.trial_id", name="fk_disclosures_trials", ondelete="CASCADE"), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("text_hash", sa.String(length=64), nullable=True),
        sa.Column("text", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("disclosure_id", name="pk_disclosures"),
    )
    # CHECK for source_type (same allowed set as doc_type)
    op.create_check_constraint("ck_disclosures_source_type", "disclosures", f"(source_type IN ({doc_list}))")
    # Indexes
    op.create_index("idx_disclosures_trial", "disclosures", ["trial_id"])
    op.create_index(
        "uq_disclosures_text_hash_notnull",
        "disclosures",
        ["text_hash"],
        unique=True,
        postgresql_where=sa.text("text_hash IS NOT NULL"),
    )


def downgrade() -> None:
    # disclosures first
    op.drop_index("uq_disclosures_text_hash_notnull", table_name="disclosures")
    op.drop_index("idx_disclosures_trial", table_name="disclosures")
    op.drop_constraint("ck_disclosures_source_type", "disclosures", type_="check")
    op.drop_constraint("pk_disclosures", "disclosures", type_="primary")
    op.drop_table("disclosures")

    # studies next
    op.drop_index("uq_studies_hash_notnull", table_name="studies")
    op.drop_index("idx_studies_extracted_jsonb", table_name="studies")
    op.drop_index("idx_studies_asset", table_name="studies")
    op.drop_index("idx_studies_trial", table_name="studies")
    op.drop_constraint("ck_studies_coverage_level", "studies", type_="check")
    op.drop_constraint("ck_studies_oa_status", "studies", type_="check")
    op.drop_constraint("ck_studies_doc_type", "studies", type_="check")
    op.drop_constraint("pk_studies", "studies", type_="primary")
    op.drop_table("studies")
