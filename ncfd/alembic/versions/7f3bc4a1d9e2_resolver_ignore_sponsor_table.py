"""resolver_ignore_sponsor table

Revision ID: 7f3bc4a1d9e2
Revises: e4587e9c596d
Create Date: 2025-08-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7f3bc4a1d9e2"
down_revision: Union[str, Sequence[str], None] = "e4587e9c596d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resolver_ignore_sponsor",
        sa.Column("pattern", sa.Text(), primary_key=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        """
        INSERT INTO resolver_ignore_sponsor (pattern, reason) VALUES
        ('NCI', 'government'),
        ('National Cancer Institute', 'government'),
        ('NIH', 'government'),
        ('National Institutes of Health', 'government'),
        ('National Institute of Health', 'government'),
        ('VA', 'government'),
        ('Department of Veterans Affairs', 'government'),
        ('Department of Defense', 'government'),
        ('DoD', 'government'),
        ('ECOG-ACRIN', 'coop group'),
        ('SWOG', 'coop group'),
        ('NRG', 'coop group'),
        ('Alliance', 'coop group')
        ON CONFLICT (pattern) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_table("resolver_ignore_sponsor")
