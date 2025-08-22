"""create resolver_features

Revision ID: 3e0f78bd8559
Revises: 0098ee120718
Create Date: 2025-08-20 12:53:14.905041

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql

# revision identifiers, used by Alembic.
revision = "3e0f78bd8559"
down_revision = "0098ee120718"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "resolver_features",
        sa.Column("rf_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("nct_id", sa.Text(), nullable=False),
        sa.Column("sponsor_text_norm", sa.Text(), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.company_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("features_jsonb", psql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("score_precal", sa.Numeric(12, 6), nullable=True),
        sa.Column("p_calibrated", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # helpful indexes
    op.create_index(
        "resolver_features_nct_idx", "resolver_features", ["nct_id"], unique=False
    )
    op.create_index(
        "resolver_features_run_idx", "resolver_features", ["run_id"], unique=False
    )
    op.create_index(
        "resolver_features_cid_idx", "resolver_features", ["company_id"], unique=False
    )
    # matches the name used in 335ae... hardening
    op.create_unique_constraint(
        "resolver_features_run_nct_cid_key",
        "resolver_features",
        ["run_id", "nct_id", "company_id"],
    )


def downgrade():
    op.drop_constraint(
        "resolver_features_run_nct_cid_key", "resolver_features", type_="unique"
    )
    op.drop_index("resolver_features_cid_idx", table_name="resolver_features")
    op.drop_index("resolver_features_run_idx", table_name="resolver_features")
    op.drop_index("resolver_features_nct_idx", table_name="resolver_features")
    op.drop_table("resolver_features")
