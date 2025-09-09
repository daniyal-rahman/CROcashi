"""create tasks priority queue

Revision ID: afc070443f13
Revises: 2247826a03d9
Create Date: 2025-09-08 14:14:17.207303

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql


# revision identifiers, used by Alembic.
revision: str = 'afc070443f13'
down_revision: Union[str, Sequence[str], None] = '2247826a03d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Table
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("task_type", sa.Text(), nullable=False),                     # e.g., PUBMED_U0U1, PUBMED_OA, STUDYCARD, SEC_SCAN
        sa.Column("task_key", sa.Text(), nullable=False),                      # idempotency key, e.g., "trial:123:OA"
        sa.Column("trial_id", sa.BigInteger(), nullable=True),
        sa.Column("company_id", sa.BigInteger(), nullable=True),
        sa.Column("priority", sa.Float(), nullable=False),                     # double precision
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("leased_by", sa.Text(), nullable=True),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("payload", psql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("task_type", "task_key", name="uq_tasks_type_key"),
        # Optional integrity guard; relax later if you expect more states
        sa.CheckConstraint(
            "status IN ('queued','leased','done','failed','parked','canceled')",
            name="ck_tasks_status_valid",
        ),
    )

    # General-purpose indexes
    op.create_index(
        "ix_tasks_status_priority_created_at",
        "tasks",
        ["status", sa.text("priority DESC"), "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_type_status_priority",
        "tasks",
        ["task_type", "status", sa.text("priority DESC"), "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_tasks_payload_gin",
        "tasks",
        ["payload"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_tasks_status_leased_until",
        "tasks",
        ["status", "leased_until"],
        unique=False,
    )

    # Partial indexes for hot paths
    op.create_index(
        "ix_tasks_queued_priority_partial",
        "tasks",
        [sa.text("priority DESC"), "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_tasks_leased_expiry_partial",
        "tasks",
        ["leased_until"],
        unique=False,
        postgresql_where=sa.text("status = 'leased'"),
    )

    # updated_at trigger to auto-bump on UPDATE
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = NOW();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tasks_set_updated_at
        BEFORE UPDATE ON tasks
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at_timestamp();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop trigger & function first
    op.execute("DROP TRIGGER IF EXISTS trg_tasks_set_updated_at ON tasks;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at_timestamp();")

    # Drop indexes
    op.drop_index("ix_tasks_leased_expiry_partial", table_name="tasks")
    op.drop_index("ix_tasks_queued_priority_partial", table_name="tasks")
    op.drop_index("ix_tasks_status_leased_until", table_name="tasks")
    op.drop_index("ix_tasks_payload_gin", table_name="tasks")
    op.drop_index("ix_tasks_type_status_priority", table_name="tasks")
    op.drop_index("ix_tasks_status_priority_created_at", table_name="tasks")

    # Drop table
    op.drop_table("tasks")
