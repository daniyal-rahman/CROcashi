"""Assets and ownership

Revision ID: 8f4433c1c1aa
Revises: a30ef603d322
Create Date: 2025-08-24 21:18:18.568473

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql


# revision identifiers, used by Alembic.
revision: str = '8f4433c1c1aa'
down_revision: Union[str, Sequence[str], None] = 'a30ef603d322'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
 

def upgrade() -> None:
    # --- assets ---
    op.create_table(
        "assets",
        sa.Column("asset_id", sa.Integer, nullable=False),
        sa.Column("names_jsonb", psql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("modality", sa.Text, nullable=True),
        sa.Column("target", sa.Text, nullable=True),
        sa.Column("moa", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("asset_id", name="pk_assets"),
    )

    # Indexes for assets
    op.create_index("idx_assets_names_jsonb", "assets", ["names_jsonb"], postgresql_using="gin")
    op.create_index("idx_assets_target", "assets", ["target"])
    op.create_index("idx_assets_moa", "assets", ["moa"])

    # --- asset_ownership ---
    op.create_table(
        "asset_ownership",
        sa.Column("ownership_id", sa.BigInteger, nullable=False),
        sa.Column("asset_id", sa.Integer, sa.ForeignKey("assets.asset_id", name="fk_asset_ownership_assets", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.company_id", name="fk_asset_ownership_companies", ondelete="CASCADE"), nullable=False),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("source", sa.Text, nullable=True),        # e.g., "SEC 8-K Item 1.01", "Press release"
        sa.Column("evidence_url", sa.Text, nullable=True),  # canonical URL to the source document
        sa.CheckConstraint(
            "(end_date IS NULL) OR (start_date IS NULL) OR (start_date <= end_date)",
            name="ck_asset_ownership_date_order",
        ),
        sa.PrimaryKeyConstraint("ownership_id", name="pk_asset_ownership"),
    )

    # Indexes for asset_ownership
    op.create_index("idx_asset_ownership_asset", "asset_ownership", ["asset_id"])
    op.create_index("idx_asset_ownership_company", "asset_ownership", ["company_id"])
    op.create_index("idx_asset_ownership_start_date", "asset_ownership", ["start_date"])


def downgrade() -> None:
    # Drop child objects first
    op.drop_index("idx_asset_ownership_start_date", table_name="asset_ownership")
    op.drop_index("idx_asset_ownership_company", table_name="asset_ownership")
    op.drop_index("idx_asset_ownership_asset", table_name="asset_ownership")
    op.drop_table("asset_ownership")

    op.drop_index("idx_assets_moa", table_name="assets")
    op.drop_index("idx_assets_target", table_name="assets")
    op.drop_index("idx_assets_names_jsonb", table_name="assets")
    op.drop_table("assets")
