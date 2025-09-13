"""merge_heads

Revision ID: 7d530c0cf176
Revises: 3651d4b376ac, 958cc8211a48
Create Date: 2025-09-13 08:46:49.099487

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d530c0cf176'
down_revision: Union[str, Sequence[str], None] = ('3651d4b376ac', '958cc8211a48')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
