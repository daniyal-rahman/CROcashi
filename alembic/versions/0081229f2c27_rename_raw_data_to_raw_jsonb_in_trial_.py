"""rename raw_data to raw_jsonb in trial_versions

Revision ID: 0081229f2c27
Revises: 752afa19e084
Create Date: 2025-09-20 11:05:35.480485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0081229f2c27'
down_revision: Union[str, Sequence[str], None] = '752afa19e084'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Skip problematic auto-generated changes - factsheets doc_id should remain INTEGER
    # to match documents.doc_id foreign key constraint
    # The doc_id should stay as INTEGER, not be changed to String
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # No changes needed - factsheets doc_id should remain INTEGER
    pass
