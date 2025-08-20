"""queue_consolidation_and_compat

- Canonicalize on review_queue
- Migrate from resolver_review_queue if present
- Partial-unique pending index

Revision ID: 924b9867b702
Revises: e4587e9c596d
Create Date: 2025-08-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "924b9867b702"
down_revision = "e4587e9c596d"
branch_labels = None
depends_on = None


def upgrade():
    # Create / align review_queue
    op.create_table(
        "review_queue",
        sa.Column("rq_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("nct_id", sa.Text, nullable=False),
        sa.Column("sponsor_text", sa.Text),
        sa.Column("sponsor_text_norm", sa.Text),
        sa.Column(
            "candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'pending'")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True)),
    )
    # Add helpful indexes
    op.create_index("review_queue_created_at_idx", "review_queue", ["created_at"], unique=False)
    op.create_index("review_queue_status_idx", "review_queue", ["status"], unique=False)
    op.create_index("review_queue_nct_idx", "review_queue", ["nct_id"], unique=False)
    op.create_index("review_queue_run_id_idx", "review_queue", ["run_id"], unique=False)
    op.execute("CREATE INDEX IF NOT EXISTS review_queue_candidates_gin ON review_queue USING gin (candidates)")
    # Status check
    op.create_check_constraint(
        "ck_review_queue_status",
        "review_queue",
        "status IN ('pending','resolved','skipped')",
    )
    # Partial-unique for pending
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_review_queue_pending_key "
        "ON review_queue (run_id, nct_id, sponsor_text_norm) WHERE status = 'pending'"
    )

    # Migrate from resolver_review_queue if it exists (safe if it doesn't)
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name='resolver_review_queue'
          ) THEN
            INSERT INTO review_queue (
              run_id, nct_id, sponsor_text, sponsor_text_norm,
              candidates, reason, status, created_at, resolved_at
            )
            SELECT run_id,
                   nct_id,
                   sponsor_text,
                   COALESCE(
                     sponsor_text_norm,
                     lower(regexp_replace(COALESCE(sponsor_text, ''), '\\s+', ' ', 'g'))
                   ),
                   COALESCE(candidates_jsonb, '[]'::jsonb),
                   COALESCE(reason, 'prob_review'),
                   COALESCE(status, 'pending'),
                   created_at,
                   resolved_at
            FROM resolver_review_queue
            ON CONFLICT DO NOTHING;

            EXECUTE 'DROP TABLE resolver_review_queue';
          END IF;
        END $$;
        """
    )


def downgrade():
    # Drop partial-unique + indexes, then table
    op.execute("DROP INDEX IF EXISTS uq_review_queue_pending_key")
    op.drop_index("review_queue_candidates_gin", table_name=None)  # created via execute; harmless if missing
    op.drop_index("review_queue_run_id_idx", table_name="review_queue")
    op.drop_index("review_queue_nct_idx", table_name="review_queue")
    op.drop_index("review_queue_status_idx", table_name="review_queue")
    op.drop_index("review_queue_created_at_idx", table_name="review_queue")
    op.drop_constraint("ck_review_queue_status", "review_queue", type_="check")
    op.drop_table("review_queue")
