"""Initial database schema.

Revision ID: 0001_initial
Revises: 
Create Date: 2024-08-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:  # noqa: D401
    """Create initial tables."""

    op.create_table(
        "companies",
        sa.Column("company_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("ticker", sa.String(length=10)),
        sa.Column("cik", sa.String(length=10)),
    )

    op.create_table(
        "assets",
        sa.Column("asset_id", sa.Integer(), primary_key=True),
        sa.Column("names_jsonb", postgresql.JSONB()),
        sa.Column("modality", sa.Text()),
        sa.Column("target", sa.Text()),
        sa.Column("moa", sa.Text()),
    )

    op.create_table(
        "trials",
        sa.Column("trial_id", sa.Integer(), primary_key=True),
        sa.Column("nct_id", sa.Text(), nullable=False, unique=True),
        sa.Column("sponsor_text", sa.Text()),
        sa.Column("sponsor_company_id", sa.Integer(), sa.ForeignKey("companies.company_id")),
        sa.Column("phase", sa.Text()),
        sa.Column("indication", sa.Text()),
        sa.Column("is_pivotal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("primary_endpoint_text", sa.Text()),
        sa.Column("est_primary_completion_date", sa.Date()),
        sa.Column("status", sa.Text()),
        sa.Column("first_posted_date", sa.Date()),
        sa.Column("last_update_posted_date", sa.Date()),
        sa.Column("intervention_types", postgresql.ARRAY(sa.Text())),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("current_sha256", sa.String(length=64)),
        sa.CheckConstraint("nct_id ~ '^NCT[0-9]{8}$'", name="chk_nct"),
    )

    op.create_table(
        "trial_versions",
        sa.Column("trial_version_id", sa.Integer(), primary_key=True),
        sa.Column("trial_id", sa.Integer(), sa.ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_update_posted_date", sa.Date()),
        sa.Column("raw_jsonb", postgresql.JSONB(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("primary_endpoint_text", sa.Text()),
        sa.Column("sample_size", sa.Integer()),
        sa.Column("analysis_plan_text", sa.Text()),
        sa.Column("changes_jsonb", postgresql.JSONB()),
        sa.UniqueConstraint("trial_id", "sha256", name="uq_trial_versions_trial_sha"),
    )
    op.create_index(
        "idx_trial_versions_trial_time",
        "trial_versions",
        ["trial_id", "captured_at"],
    )
    op.create_index(
        "idx_trial_versions_hash",
        "trial_versions",
        ["sha256"],
    )

    op.create_table(
        "ctgov_history_versions",
        sa.Column("trial_id", sa.Integer(), sa.ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version_rank", sa.Integer(), primary_key=True),
        sa.Column("submitted_date", sa.Date()),
        sa.Column("url", sa.Text()),
    )

    op.create_table(
        "ctgov_ingest_state",
        sa.Column("id", sa.Boolean(), primary_key=True, server_default=sa.true()),
        sa.Column("cursor_last_update_posted", sa.Date()),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "ingest_runs",
        sa.Column("run_id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("since_date", sa.Date()),
        sa.Column("until_date", sa.Date()),
        sa.Column("total_returned", sa.Integer()),
        sa.Column("total_processed", sa.Integer()),
        sa.Column("notes", sa.Text()),
    )

    op.create_table(
        "studies",
        sa.Column("study_id", sa.Integer(), primary_key=True),
        sa.Column("trial_id", sa.Integer(), sa.ForeignKey("trials.trial_id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.asset_id")),
        sa.Column("doc_type", sa.Text()),
        sa.Column("citation", sa.Text()),
        sa.Column("year", sa.Integer()),
        sa.Column("url", sa.Text()),
        sa.Column("oa_status", sa.Text()),
        sa.Column("extracted_jsonb", postgresql.JSONB()),
        sa.Column("notes_md", sa.Text()),
        sa.Column("coverage_level", sa.Integer()),
    )

    op.create_table(
        "signals",
        sa.Column("trial_id", sa.Integer(), sa.ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("s_id", sa.Text(), primary_key=True),
        sa.Column("value", sa.Float()),
        sa.Column("severity", sa.Text()),
        sa.Column("evidence_span", sa.Text()),
        sa.Column("source_study_id", sa.Integer(), sa.ForeignKey("studies.study_id")),
    )

    op.create_table(
        "gates",
        sa.Column("trial_id", sa.Integer(), sa.ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("g_id", sa.Text(), primary_key=True),
        sa.Column("fired_bool", sa.Boolean(), nullable=False),
        sa.Column("supporting_s_ids", postgresql.ARRAY(sa.Text())),
        sa.Column("lr_used", sa.Float()),
        sa.Column("rationale_text", sa.Text()),
    )

    op.create_table(
        "scores",
        sa.Column("trial_id", sa.Integer(), sa.ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("run_id", sa.Integer(), primary_key=True),
        sa.Column("prior_pi", sa.Float()),
        sa.Column("logit_prior", sa.Float()),
        sa.Column("sum_log_lr", sa.Float()),
        sa.Column("logit_post", sa.Float()),
        sa.Column("p_fail", sa.Float()),
    )

    op.create_table(
        "asset_ownership",
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.asset_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.company_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("start_date", sa.Date(), primary_key=True),
        sa.Column("end_date", sa.Date()),
        sa.Column("source", sa.Text()),
        sa.Column("evidence_url", sa.Text()),
    )

    op.create_table(
        "patents",
        sa.Column("patent_id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.asset_id", ondelete="CASCADE")),
        sa.Column("family_id", sa.Text()),
        sa.Column("jurisdiction", sa.Text()),
        sa.Column("number", sa.Text()),
        sa.Column("earliest_priority_date", sa.Date()),
        sa.Column("assignees", postgresql.ARRAY(sa.Text())),
        sa.Column("inventors", postgresql.ARRAY(sa.Text())),
        sa.Column("status", sa.Text()),
    )

    op.create_table(
        "patent_assignments",
        sa.Column("assignment_id", sa.Integer(), primary_key=True),
        sa.Column("patent_id", sa.Integer(), sa.ForeignKey("patents.patent_id", ondelete="CASCADE"), nullable=False),
        sa.Column("assignor", sa.Text()),
        sa.Column("assignee", sa.Text()),
        sa.Column("exec_date", sa.Date()),
        sa.Column("type", sa.Text()),
        sa.Column("source_url", sa.Text()),
    )

    op.create_table(
        "labels",
        sa.Column("trial_id", sa.Integer(), sa.ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("event_date", sa.Date(), primary_key=True),
        sa.Column("primary_outcome_success_bool", sa.Boolean()),
        sa.Column("price_move_5d", sa.Float()),
        sa.Column("label_source_url", sa.Text()),
    )

    op.create_table(
        "catalysts",
        sa.Column("trial_id", sa.Integer(), sa.ForeignKey("trials.trial_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("window_start", sa.Date(), primary_key=True),
        sa.Column("window_end", sa.Date()),
        sa.Column("certainty", sa.Float()),
        sa.Column("sources", postgresql.ARRAY(sa.Text())),
    )


def downgrade() -> None:  # noqa: D401
    """Drop all tables."""

    op.drop_table("catalysts")
    op.drop_table("labels")
    op.drop_table("patent_assignments")
    op.drop_table("patents")
    op.drop_table("asset_ownership")
    op.drop_table("scores")
    op.drop_table("gates")
    op.drop_table("signals")
    op.drop_table("studies")
    op.drop_table("ingest_runs")
    op.drop_table("ctgov_ingest_state")
    op.drop_table("ctgov_history_versions")
    op.drop_index("idx_trial_versions_hash", table_name="trial_versions")
    op.drop_index("idx_trial_versions_trial_time", table_name="trial_versions")
    op.drop_table("trial_versions")
    op.drop_table("trials")
    op.drop_table("assets")
    op.drop_table("companies")

