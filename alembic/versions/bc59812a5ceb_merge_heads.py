"""merge heads

Revision ID: bc59812a5ceb
Revises: clean_pattern_families_001, ed8c75a98013
Create Date: 2025-09-15 23:39:01.174902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc59812a5ceb'
down_revision: Union[str, Sequence[str], None] = ('clean_pattern_families_001', 'ed8c75a98013')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
