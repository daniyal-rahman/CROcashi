"""make_exchange_nullable

Revision ID: 5fa221363d83
Revises: 571937b83dd7
Create Date: 2025-08-25 18:05:53.927558

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5fa221363d83'
down_revision: Union[str, Sequence[str], None] = '571937b83dd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
