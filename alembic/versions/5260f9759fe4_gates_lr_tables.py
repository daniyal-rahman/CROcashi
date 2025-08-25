"""Gates LR Tables

Revision ID: 5260f9759fe4
Revises: 29546d6d96fa
Create Date: 2025-08-24 21:38:22.883952

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5260f9759fe4'
down_revision: Union[str, Sequence[str], None] = '29546d6d96fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from sqlalchemy.dialects import postgresql as psql

G_IDS = ("G1", "G2", "G3", "G4")
S_IDS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9")

def upgrade() -> None:
    # -------------------
    # gates (composite gate firings, per trial)
    # -------------------
    op.create_table(
        "gates",
        sa.Column("gate_row_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column(
            "trial_id",
            sa.Integer,
            sa.ForeignKey("trials.trial_id", name="fk_gates_trials", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("g_id", sa.String(length=4), nullable=False),                # 'G1'..'G4'
        sa.Column("fired_bool", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("supporting_s_ids", psql.ARRAY(sa.Text), nullable=True),     # must be subset of S1..S9
        sa.Column("lr_used", sa.Numeric(10, 6), nullable=True),
        sa.Column("rationale_text", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("gate_row_id", name="pk_gates"),
        sa.UniqueConstraint("trial_id", "g_id", name="uq_gates_trial_g"),
    )
    # CHECK: g_id in allowed set
    g_list = ", ".join(f"'{v}'" for v in G_IDS)
    op.create_check_constraint("ck_gates_g_id_allowed", "gates", f"(g_id IN ({g_list}))")
    # CHECK: supporting_s_ids ⊆ allowed S set (or NULL)
    s_list = ", ".join(f"'{v}'" for v in S_IDS)
    op.create_check_constraint(
        "ck_gates_supporting_s_ids_subset",
        "gates",
        f"(supporting_s_ids IS NULL OR supporting_s_ids <@ ARRAY[{s_list}]::text[])",
    )
    op.create_index("idx_gates_trial", "gates", ["trial_id"])

    # -------------------
    # scores (posterior probability per run)
    # -------------------
    op.create_table(
        "scores",
        sa.Column("score_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column(
            "trial_id",
            sa.Integer,
            sa.ForeignKey("trials.trial_id", name="fk_scores_trials", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("prior_pi", sa.Numeric(5, 4), nullable=True),
        sa.Column("logit_prior", sa.Numeric(10, 6), nullable=True),
        sa.Column("sum_log_lr", sa.Numeric(10, 6), nullable=True),
        sa.Column("logit_post", sa.Numeric(10, 6), nullable=True),
        sa.Column("p_fail", sa.Numeric(5, 4), nullable=True),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("score_id", name="pk_scores"),
    )
    op.create_index("idx_scores_trial", "scores", ["trial_id"])
    op.create_index("idx_scores_run_id", "scores", ["run_id"])
    op.create_index("idx_scores_timestamp", "scores", ["timestamp"])

    # -------------------
    # lr_tables (calibrated likelihood ratios)
    # -------------------
    op.create_table(
        "lr_tables",
        sa.Column("lr_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column("scope", sa.String(length=10), nullable=False),            # 'gate' or 'signal'
        sa.Column("id_code", sa.String(length=8), nullable=False),           # 'G1'.. or 'S1'..
        sa.Column("universe_tag", sa.Text, nullable=False),                  # e.g., 'US_smallcap_pivotal_2018_2023'
        sa.Column("lr_value", sa.Numeric(10, 6), nullable=False),
        sa.Column("ci_low", sa.Numeric(10, 6), nullable=True),
        sa.Column("ci_high", sa.Numeric(10, 6), nullable=True),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.PrimaryKeyConstraint("lr_id", name="pk_lr_tables"),
    )
    # CHECK: scope allowed
    op.create_check_constraint(
        "ck_lr_tables_scope",
        "lr_tables",
        "(scope IN ('gate','signal'))",
    )
    # CHECK: id_code matches scope (G* for gate, S* for signal)
    op.create_check_constraint(
        "ck_lr_tables_id_code_matches_scope",
        "lr_tables",
        f"((scope = 'gate' AND id_code IN ({g_list})) OR (scope = 'signal' AND id_code IN ({s_list})))",
    )
    # Optional: date order check
    op.create_check_constraint(
        "ck_lr_tables_date_order",
        "lr_tables",
        "(effective_to IS NULL OR effective_from <= effective_to)",
    )
    # Helpful composite index for lookups
    op.create_index(
        "idx_lr_tables_lookup",
        "lr_tables",
        ["id_code", "universe_tag", "effective_from"],
    )


def downgrade() -> None:
    # Drop in reverse dependency order

    # lr_tables
    op.drop_index("idx_lr_tables_lookup", table_name="lr_tables")
    op.drop_constraint("ck_lr_tables_date_order", "lr_tables", type_="check")
    op.drop_constraint("ck_lr_tables_id_code_matches_scope", "lr_tables", type_="check")
    op.drop_constraint("ck_lr_tables_scope", "lr_tables", type_="check")
    op.drop_constraint("pk_lr_tables", "lr_tables", type_="primary")
    op.drop_table("lr_tables")

    # scores
    op.drop_index("idx_scores_timestamp", table_name="scores")
    op.drop_index("idx_scores_run_id", table_name="scores")
    op.drop_index("idx_scores_trial", table_name="scores")
    op.drop_constraint("pk_scores", "scores", type_="primary")
    op.drop_table("scores")

    # gates
    op.drop_index("idx_gates_trial", table_name="gates")
    op.drop_constraint("ck_gates_supporting_s_ids_subset", "gates", type_="check")
    op.drop_constraint("ck_gates_g_id_allowed", "gates", type_="check")
    op.drop_constraint("uq_gates_trial_g", "gates", type_="unique")
    op.drop_constraint("pk_gates", "gates", type_="primary")
    op.drop_table("gates")
