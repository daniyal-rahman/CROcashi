"""resolver_ignore_sponsor

Revision ID: 0272ed4ed4ec
Revises: 583de950b814
Create Date: 2025-08-25 16:12:00.591764

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0272ed4ed4ec'
down_revision: Union[str, Sequence[str], None] = '583de950b814'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Create resolver_ignore_sponsor table."""
    op.create_table(
        "resolver_ignore_sponsor",
        sa.Column("pattern", sa.Text(), primary_key=True),
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop resolver_ignore_sponsor table."""
    op.drop_table("resolver_ignore_sponsor")
