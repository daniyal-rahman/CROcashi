"""Signals and Evidence

Revision ID: 29546d6d96fa
Revises: 34689bd20f02
Create Date: 2025-08-24 21:36:13.819161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29546d6d96fa'
down_revision: Union[str, Sequence[str], None] = '34689bd20f02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from sqlalchemy.dialects import postgresql as psql

S_IDS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9")
SEVERITIES = ("H", "M", "L")


def upgrade() -> None:
    # -------------------
    # signals (primitive flags S1–S9; 1 row per trial per S)
    # -------------------
    op.create_table(
        "signals",
        sa.Column("signal_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column(
            "trial_id",
            sa.Integer,
            sa.ForeignKey("trials.trial_id", name="fk_signals_trials", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("s_id", sa.String(length=4), nullable=False),          # 'S1'..'S9'
        sa.Column("value", sa.Numeric(10, 6), nullable=True),            # optional numeric payload
        sa.Column("severity", sa.String(length=1), nullable=False),      # 'H','M','L'
        sa.Column("fired_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", psql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("signal_id", name="pk_signals"),
        sa.UniqueConstraint("trial_id", "s_id", name="uq_signals_trial_s_id"),
    )
    # CHECKs (embed literal lists)
    s_list = ", ".join(f"'{v}'" for v in S_IDS)
    sev_list = ", ".join(f"'{v}'" for v in SEVERITIES)
    op.create_check_constraint("ck_signals_s_id_allowed", "signals", f"(s_id IN ({s_list}))")
    op.create_check_constraint("ck_signals_severity_allowed", "signals", f"(severity IN ({sev_list}))")
    # Helpful index
    op.create_index("idx_signals_trial", "signals", ["trial_id"])

    # -------------------
    # signal_evidence (many evidence rows per signal)
    # -------------------
    op.create_table(
        "signal_evidence",
        sa.Column("evidence_id", sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column(
            "signal_id",
            sa.BigInteger,
            sa.ForeignKey("signals.signal_id", name="fk_signal_evidence_signals", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_study_id",
            sa.BigInteger,
            sa.ForeignKey("studies.study_id", name="fk_signal_evidence_studies", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("evidence_span", sa.Text, nullable=True),  # e.g., "p.3, Table 2, ORR row"
        sa.Column("metadata", psql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("evidence_id", name="pk_signal_evidence"),
    )
    op.create_index("idx_signal_evidence_signal", "signal_evidence", ["signal_id"])
    op.create_index("idx_signal_evidence_study", "signal_evidence", ["source_study_id"])


def downgrade() -> None:
    # Drop children first
    op.drop_index("idx_signal_evidence_study", table_name="signal_evidence")
    op.drop_index("idx_signal_evidence_signal", table_name="signal_evidence")
    op.drop_constraint("pk_signal_evidence", "signal_evidence", type_="primary")
    op.drop_table("signal_evidence")

    # Then signals
    op.drop_index("idx_signals_trial", table_name="signals")
    op.drop_constraint("ck_signals_severity_allowed", "signals", type_="check")
    op.drop_constraint("ck_signals_s_id_allowed", "signals", type_="check")
    op.drop_constraint("uq_signals_trial_s_id", "signals", type_="unique")
    op.drop_constraint("pk_signals", "signals", type_="primary")
    op.drop_table("signals")
