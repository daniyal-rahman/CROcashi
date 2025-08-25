"""Trials and versioning

Revision ID: cc44d2e61b7e
Revises: 8f4433c1c1aa
Create Date: 2025-08-24 21:21:07.734239

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc44d2e61b7e'
down_revision: Union[str, Sequence[str], None] = '8f4433c1c1aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

from sqlalchemy.dialects import postgresql as psql

# PHASE_ALLOWED = ("P2", "P2B", "P2/3", "P3")
# PHASE_ALLOWED = ("PHASE2", "PHASE3", "PHASE2_PHASE3")
# TRIAL_STATUS_ALLOWED = (
#     "NOT YET RECRUITING",
#     "RECRUITING",
#     "ENROLLING BY INVITATION",
#     "ACTIVE, NOT RECRUITING",
#     "COMPLETED",
#     "SUSPENDED",
#     "TERMINATED",
#     "WITHDRAWN",
#     "UNKNOWN STATUS",
# )
PHASE_ALLOWED = (
    'PHASE2',
    'PHASE2B',
    'PHASE2_3',          # your ETL is producing this
    'PHASE2_PHASE3',     # keep this too if any upstream variant appears
    'PHASE3',
    'PHASE4',
)

TRIAL_STATUS_ALLOWED = (
    'NOT_YET_RECRUITING',
    'RECRUITING',
    'ENROLLING_BY_INVITATION',
    'ACTIVE_NOT_RECRUITING',
    'COMPLETED',
    'SUSPENDED',
    'TERMINATED',
    'WITHDRAWN',
    'UNKNOWN_STATUS'
)
def upgrade() -> None:
    # -------------------
    # trials
    # -------------------
    op.create_table(
        "trials",
        sa.Column("trial_id", sa.Integer, nullable=False),
        sa.Column("nct_id", sa.String(length=20), nullable=False),
        sa.Column("brief_title", sa.Text, nullable=True),
        sa.Column("official_title", sa.Text, nullable=True),
        sa.Column("sponsor_text", sa.Text, nullable=True),
        sa.Column(
            "sponsor_company_id",
            sa.Integer,
            sa.ForeignKey("companies.company_id", name="fk_trials_companies", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("phase", sa.String(length=8), nullable=True),
        sa.Column("indication", sa.Text, nullable=True),
        sa.Column("is_pivotal", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("primary_endpoint_text", sa.Text, nullable=True),
        sa.Column("est_primary_completion_date", sa.Date, nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("first_posted_date", sa.Date, nullable=True),
        sa.Column("last_update_posted_date", sa.Date, nullable=True),
        sa.Column("results_first_posted_date", sa.Date, nullable=True),
        sa.Column("has_results", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("lead_sponsor_class", sa.Text, nullable=True),
        sa.Column("responsible_party", sa.Text, nullable=True),
        sa.Column("allocation", sa.Text, nullable=True),
        sa.Column("masking", sa.Text, nullable=True),
        sa.Column("num_arms", sa.Integer, nullable=True),
        sa.Column("intervention_types", psql.ARRAY(sa.Text), nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("current_sha256", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("trial_id", name="pk_trials"),
        sa.UniqueConstraint("nct_id", name="uq_trials_nct_id"),
    )
    # CHECK constraints with literal lists (no bound params)
    phase_list = ", ".join(f"'{v}'" for v in PHASE_ALLOWED)
    status_list = ", ".join(f"'{v}'" for v in TRIAL_STATUS_ALLOWED)
    op.create_check_constraint(
        "ck_trials_phase_allowed",
        "trials",
        f"(phase IS NULL OR phase IN ({phase_list}))",
    )
    op.create_check_constraint(
        "ck_trials_status_allowed",
        "trials",
        f"(status IS NULL OR status IN ({status_list}))",
    )
    # Indexes
    op.create_index("idx_trials_sponsor_company", "trials", ["sponsor_company_id"])
    op.create_index("idx_trials_est_pcd", "trials", ["est_primary_completion_date"])
    op.create_index("idx_trials_phase", "trials", ["phase"])
    op.create_index("idx_trials_status", "trials", ["status"])
    op.create_index("idx_trials_last_update", "trials", ["last_update_posted_date"])

    # -------------------
    # trial_versions
    # -------------------
    op.create_table(
        "trial_versions",
        sa.Column("trial_version_id", sa.Integer, nullable=False),
        sa.Column(
            "trial_id",
            sa.Integer,
            sa.ForeignKey("trials.trial_id", name="fk_trial_versions_trials", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("raw_jsonb", psql.JSONB, nullable=True),
        sa.Column("last_update_posted_date", sa.Date, nullable=True),
        sa.Column("primary_endpoint_text", sa.Text, nullable=True),
        sa.Column("sample_size", sa.Integer, nullable=True),
        sa.Column("analysis_plan_text", sa.Text, nullable=True),
        sa.Column("changes_jsonb", psql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("changed_primary_endpoint", sa.Boolean, nullable=True),
        sa.Column("changed_sample_size", sa.Boolean, nullable=True),
        sa.Column("sample_size_delta", sa.Integer, nullable=True),
        sa.Column("changed_analysis_plan", sa.Boolean, nullable=True),
        sa.Column("metadata_jsonb", psql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("trial_version_id", name="pk_trial_versions"),
        sa.UniqueConstraint("trial_id", "sha256", name="uq_trial_version_sha"),
    )
    op.create_index("idx_trial_versions_ts", "trial_versions", ["trial_id", "captured_at"])


def downgrade() -> None:
    # Drop children first
    op.drop_index("idx_trial_versions_ts", table_name="trial_versions")
    op.drop_constraint("uq_trial_version_sha", "trial_versions", type_="unique")
    op.drop_constraint("pk_trial_versions", "trial_versions", type_="primary")
    op.drop_table("trial_versions")

    # trials
    op.drop_index("idx_trials_last_update", table_name="trials")
    op.drop_index("idx_trials_status", table_name="trials")
    op.drop_index("idx_trials_phase", table_name="trials")
    op.drop_index("idx_trials_est_pcd", table_name="trials")
    op.drop_index("idx_trials_sponsor_company", table_name="trials")

    op.drop_constraint("ck_trials_status_allowed", "trials", type_="check")
    op.drop_constraint("ck_trials_phase_allowed", "trials", type_="check")
    op.drop_constraint("uq_trials_nct_id", "trials", type_="unique")
    op.drop_constraint("pk_trials", "trials", type_="primary")
    op.drop_table("trials")
