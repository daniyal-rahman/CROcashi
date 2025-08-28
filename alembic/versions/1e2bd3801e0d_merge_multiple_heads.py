"""merge multiple heads

Revision ID: 1e2bd3801e0d
Revises: add_lit_pipeline_exec, add_checkpoint2_4_fields
Create Date: 2025-08-28 14:30:05.739156

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e2bd3801e0d'
down_revision: Union[str, Sequence[str], None] = ('add_lit_pipeline_exec', 'add_checkpoint2_4_fields')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
