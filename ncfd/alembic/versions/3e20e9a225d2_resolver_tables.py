"""resolver tables

Revision ID: 3e20e9a225d2
Revises: c83a9699908c
Create Date: 2025-08-17 20:31:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3e20e9a225d2"
down_revision: Union[str, Sequence[str], None] = "c83a9699908c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Extensions we rely on (safe/idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # -----------------------------
    # resolver_decisions
    # -----------------------------
    op.create_table(
        "resolver_decisions",
        sa.Column("decision_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("nct_id", sa.Text(), nullable=False),
        sa.Column("sponsor_text", sa.Text(), nullable=False),
        sa.Column("sponsor_text_norm", sa.Text(), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),  # change to sa.BigInteger() if companies.company_id is BIGINT
            sa.ForeignKey("companies.company_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("match_type", sa.Text(), nullable=False),  # deterministic:* | probabilistic:* | asset_backstop:* | no_match
        sa.Column("p_match", sa.Float(), nullable=True),
        sa.Column("top2_margin", sa.Float(), nullable=True),
        sa.Column(
            "features_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "evidence_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("decided_by", sa.Text(), nullable=False),  # auto | human | llm
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("notes_md", sa.Text(), nullable=True),
    )

    op.create_unique_constraint(
        "uq_resolver_decision_key",
        "resolver_decisions",
        ["run_id", "nct_id", "sponsor_text_norm"],
    )
    op.create_index("ix_resolver_decisions_company", "resolver_decisions", ["company_id"], unique=False)
    op.create_index("ix_resolver_decisions_nct", "resolver_decisions", ["nct_id"], unique=False)
    # Speed lookup by normalized sponsor (trigram)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resolver_decisions_sponsor_norm_trgm "
        "ON resolver_decisions USING gin (sponsor_text_norm gin_trgm_ops)"
    )
    # Optional JSONB GIN for features
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resolver_decisions_features_gin "
        "ON resolver_decisions USING gin (features_jsonb)"
    )
    # Cheap enum for decided_by
    op.create_check_constraint(
        "ck_resolver_decisions_decided_by",
        "resolver_decisions",
        "decided_by IN ('auto','human','llm')",
    )
    # Probability bounds
    op.create_check_constraint(
        "ck_resolver_decisions_p_bounds",
        "resolver_decisions",
        "(p_match IS NULL) OR (p_match >= 0.0 AND p_match <= 1.0)",
    )
    # Run/type compound index for reporting
    op.create_index("ix_resolver_decisions_run_type", "resolver_decisions", ["run_id", "match_type"], unique=False)

    # -----------------------------
    # resolver_review_queue
    # -----------------------------
    op.create_table(
        "resolver_review_queue",
        sa.Column("rq_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("nct_id", sa.Text(), nullable=False),
        sa.Column("sponsor_text", sa.Text(), nullable=False),
        sa.Column("sponsor_text_norm", sa.Text(), nullable=False),
        sa.Column(
            "candidates_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reason", sa.Text(), nullable=False),  # multi-deterministic | prob_review | asset_review | no_match
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),  # pending|resolved|skipped
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_review_queue_status", "resolver_review_queue", ["status"], unique=False)
    op.create_index("ix_review_queue_run", "resolver_review_queue", ["run_id"], unique=False)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_review_queue_candidates_gin "
        "ON resolver_review_queue USING gin (candidates_jsonb)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_review_queue_sponsor_norm_trgm "
        "ON resolver_review_queue USING gin (sponsor_text_norm gin_trgm_ops)"
    )
    # Prevent duplicate pending items for same key in a run
    op.create_index(
        "uq_review_queue_pending_key",
        "resolver_review_queue",
        ["run_id", "nct_id", "sponsor_text_norm"],
        unique=True,
        postgresql_where=sa.text("status='pending'"),
    )
    # Status enum
    op.create_check_constraint(
        "ck_review_queue_status",
        "resolver_review_queue",
        "status IN ('pending','resolved','skipped')",
    )

    # -----------------------------
    # resolver_labels (for training/eval)
    # -----------------------------
    op.create_table(
        "resolver_labels",
        sa.Column("label_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("nct_id", sa.Text(), nullable=False),
        sa.Column("sponsor_text_norm", sa.Text(), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),  # change to sa.BigInteger() if companies.company_id is BIGINT
            sa.ForeignKey("companies.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_match", sa.Boolean(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),  # deterministic | human | audit | llm
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_labels_key", "resolver_labels", ["nct_id", "sponsor_text_norm"], unique=False)
    op.create_index("ix_labels_company", "resolver_labels", ["company_id"], unique=False)
    op.create_index("ix_resolver_labels_source_time", "resolver_labels", ["source", "created_at"], unique=False)
    op.create_check_constraint(
        "ck_resolver_labels_source",
        "resolver_labels",
        "source IN ('deterministic','human','audit','llm')",
    )

    # -----------------------------
    # resolver_features (per-candidate feature capture)
    # -----------------------------
    op.create_table(
        "resolver_features",
        sa.Column("row_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("nct_id", sa.Text(), nullable=False),
        sa.Column("sponsor_text_norm", sa.Text(), nullable=False),
        sa.Column(
            "company_id",
            sa.Integer(),  # change to sa.BigInteger() if companies.company_id is BIGINT
            sa.ForeignKey("companies.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "features_jsonb",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("score_precal", sa.Float(), nullable=True),
        sa.Column("p_calibrated", sa.Float(), nullable=True),
    )
    op.create_index("ix_resolver_features_run", "resolver_features", ["run_id"], unique=False)
    op.create_index("ix_resolver_features_company", "resolver_features", ["company_id"], unique=False)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_resolver_features_features_gin "
        "ON resolver_features USING gin (features_jsonb)"
    )
    op.create_check_constraint(
        "ck_resolver_features_p_bounds",
        "resolver_features",
        "(p_calibrated IS NULL) OR (p_calibrated >= 0.0 AND p_calibrated <= 1.0)",
    )


def downgrade() -> None:
    """Downgrade schema."""

    # resolver_features
    op.drop_constraint("ck_resolver_features_p_bounds", "resolver_features", type_="check")
    op.drop_index("ix_resolver_features_features_gin", table_name="resolver_features")
    op.drop_index("ix_resolver_features_company", table_name="resolver_features")
    op.drop_index("ix_resolver_features_run", table_name="resolver_features")
    op.drop_table("resolver_features")

    # resolver_labels
    op.drop_constraint("ck_resolver_labels_source", "resolver_labels", type_="check")
    op.drop_index("ix_resolver_labels_source_time", table_name="resolver_labels")
    op.drop_index("ix_labels_company", table_name="resolver_labels")
    op.drop_index("ix_labels_key", table_name="resolver_labels")
    op.drop_table("resolver_labels")

    # resolver_review_queue
    op.drop_constraint("ck_review_queue_status", "resolver_review_queue", type_="check")
    op.drop_index("uq_review_queue_pending_key", table_name="resolver_review_queue")
    op.drop_index("ix_review_queue_sponsor_norm_trgm", table_name="resolver_review_queue")
    op.drop_index("ix_review_queue_candidates_gin", table_name="resolver_review_queue")
    op.drop_index("ix_review_queue_run", table_name="resolver_review_queue")
    op.drop_index("ix_review_queue_status", table_name="resolver_review_queue")
    op.drop_table("resolver_review_queue")

    # resolver_decisions
    op.drop_index("ix_resolver_decisions_run_type", table_name="resolver_decisions")
    op.drop_constraint("ck_resolver_decisions_p_bounds", "resolver_decisions", type_="check")
    op.drop_constraint("ck_resolver_decisions_decided_by", "resolver_decisions", type_="check")
    op.drop_index("ix_resolver_decisions_features_gin", table_name="resolver_decisions")
    op.drop_index("ix_resolver_decisions_sponsor_norm_trgm", table_name="resolver_decisions")
    op.drop_index("ix_resolver_decisions_nct", table_name="resolver_decisions")
    op.drop_index("ix_resolver_decisions_company", table_name="resolver_decisions")
    op.drop_constraint("uq_resolver_decision_key", "resolver_decisions", type_="unique")
    op.drop_table("resolver_decisions")

    # (We keep pg_trgm installed; safe to leave in place.)
