"""merge branches

Revision ID: 420c49ebb45a
Revises: add_text_original_to_base_spans, add_uspto_patent_extensions
Create Date: 2025-09-06 01:01:38.064201

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '420c49ebb45a'
down_revision: Union[str, Sequence[str], None] = ('add_text_original_to_base_spans', 'add_uspto_patent_extensions')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
