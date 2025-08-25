"""Catalysts Labels and Markets

Revision ID: 3a0381c42074
Revises: 5260f9759fe4
Create Date: 2025-08-24 21:41:01.709031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a0381c42074'
down_revision: Union[str, Sequence[str], None] = '5260f9759fe4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from sqlalchemy.dialects import postgresql as psql


CERTAINTY = ("low", "med", "high")


def upgrade() -> None:
    # -------------------
    # catalysts
    # -------------------
    op.create_table(
        "catalysts",
        sa.Column("catalyst_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column(
            "trial_id",
            sa.Integer,
            sa.ForeignKey("trials.trial_id", name="fk_catalysts_trials", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("window_start", sa.Date, nullable=True),
        sa.Column("window_end", sa.Date, nullable=True),
        sa.Column("certainty", sa.String(length=8), nullable=True),
        sa.Column("sources", psql.ARRAY(sa.Text), nullable=True),  # URLs
        sa.PrimaryKeyConstraint("catalyst_id", name="pk_catalysts"),
    )
    # CHECKs
    cert_list = ", ".join(f"'{v}'" for v in CERTAINTY)
    op.create_check_constraint(
        "ck_catalysts_certainty_allowed",
        "catalysts",
        f"(certainty IS NULL OR certainty IN ({cert_list}))",
    )
    op.create_check_constraint(
        "ck_catalysts_date_order",
        "catalysts",
        "(window_end IS NULL OR window_start IS NULL OR window_start <= window_end)",
    )
    # Indexes
    op.create_index("idx_catalysts_trial", "catalysts", ["trial_id"])
    op.create_index("idx_catalysts_window_start", "catalysts", ["window_start"])

    # -------------------
    # labels (ground truth for backtests)
    # -------------------
    op.create_table(
        "labels",
        sa.Column("label_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column(
            "trial_id",
            sa.Integer,
            sa.ForeignKey("trials.trial_id", name="fk_labels_trials", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_date", sa.Date, nullable=True),
        sa.Column("primary_outcome_success_bool", sa.Boolean, nullable=True),
        sa.Column("price_move_5d", sa.Numeric(10, 4), nullable=True),
        sa.Column("label_source_url", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("label_id", name="pk_labels"),
    )
    op.create_index("idx_labels_trial", "labels", ["trial_id"])
    op.create_index("idx_labels_event_date", "labels", ["event_date"])

    # -------------------
    # markets (optional analytics)
    # -------------------
    op.create_table(
        "markets",
        sa.Column("mkt_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("market_cap", sa.Numeric(20, 4), nullable=True),
        sa.Column("price", sa.Numeric(14, 6), nullable=True),
        sa.PrimaryKeyConstraint("mkt_id", name="pk_markets"),
    )
    # Composite index for lookups; no uniqueness enforced (you can add later if you store only EOD)
    op.create_index("idx_markets_ticker_date", "markets", ["ticker", "date"])


def downgrade() -> None:
    # Drop in reverse dependency order (none depend on each other except FKs to trials)

    # markets
    op.drop_index("idx_markets_ticker_date", table_name="markets")
    op.drop_constraint("pk_markets", "markets", type_="primary")
    op.drop_table("markets")

    # labels
    op.drop_index("idx_labels_event_date", table_name="labels")
    op.drop_index("idx_labels_trial", table_name="labels")
    op.drop_constraint("pk_labels", "labels", type_="primary")
    op.drop_table("labels")

    # catalysts
    op.drop_index("idx_catalysts_window_start", table_name="catalysts")
    op.drop_index("idx_catalysts_trial", table_name="catalysts")
    op.drop_constraint("ck_catalysts_date_order", "catalysts", type_="check")
    op.drop_constraint("ck_catalysts_certainty_allowed", "catalysts", type_="check")
    op.drop_constraint("pk_catalysts", "catalysts", type_="primary")
    op.drop_table("catalysts")
