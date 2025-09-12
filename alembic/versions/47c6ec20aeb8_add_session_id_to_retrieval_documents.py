"""add_session_id_to_retrieval_documents

Revision ID: 47c6ec20aeb8
Revises: 73abcc2b7bd3
Create Date: 2025-09-11 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '47c6ec20aeb8'
down_revision: Union[str, Sequence[str], None] = '73abcc2b7bd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add session_id column to retrieval_documents."""
    op.add_column('retrieval_documents', sa.Column('session_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_retrieval_documents_session_id', 'retrieval_documents', 'retrieval_sessions', ['session_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_retrieval_documents_session_id', 'retrieval_documents', ['session_id'])


def downgrade() -> None:
    """Downgrade schema - Remove session_id column from retrieval_documents."""
    op.drop_index('ix_retrieval_documents_session_id', 'retrieval_documents')
    op.drop_constraint('fk_retrieval_documents_session_id', 'retrieval_documents', type_='foreignkey')
    op.drop_column('retrieval_documents', 'session_id')