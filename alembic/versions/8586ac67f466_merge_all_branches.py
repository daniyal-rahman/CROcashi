"""merge all branches

Revision ID: 8586ac67f466
Revises: 420c49ebb45a, 9c3d4e5f6g7h
Create Date: 2025-09-06 01:01:42.271090

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8586ac67f466'
down_revision: Union[str, Sequence[str], None] = ('420c49ebb45a', '9c3d4e5f6g7h')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
