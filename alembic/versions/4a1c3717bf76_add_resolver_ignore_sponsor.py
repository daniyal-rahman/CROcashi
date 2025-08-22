"""add resolver_ignore_sponsor

Revision ID: 4a1c3717bf76
Revises: 795f73371565
Create Date: 2025-08-20 04:58:43.642060

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "4a1c3717bf76"
down_revision = "795f73371565"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resolver_ignore_sponsor",
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("pattern", name="uq_resolver_ignore_sponsor_pattern"),
    )

    # Optional seed examples (safe to remove if you prefer empty)
    op.execute(
        """
        INSERT INTO resolver_ignore_sponsor(pattern, comment) VALUES
          ('\\b(National Institutes? of Health|NIH)\\b', 'Government sponsor'),
          ('\\b(University|Hospital|Medical Center)\\b', 'Academic sponsor');
        """
    )


def downgrade() -> None:
    op.drop_table("resolver_ignore_sponsor")
