"""merge_resolver_and_processing_queue

Revision ID: ed8c75a98013
Revises: 117fe225c48e, a0565a1faa0e
Create Date: 2025-09-15 22:09:30.038830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed8c75a98013'
down_revision: Union[str, Sequence[str], None] = ('117fe225c48e', 'a0565a1faa0e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
