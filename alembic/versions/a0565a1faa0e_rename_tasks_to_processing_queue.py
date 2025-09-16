"""rename_tasks_to_processing_queue

Revision ID: a0565a1faa0e
Revises: f44bfaf9c8f7
Create Date: 2025-09-15 20:47:46.182472

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0565a1faa0e'
down_revision: Union[str, Sequence[str], None] = 'f44bfaf9c8f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename tasks table to processing_queue."""
    op.rename_table('tasks', 'processing_queue')


def downgrade() -> None:
    """Rename processing_queue table back to tasks."""
    op.rename_table('processing_queue', 'tasks')
