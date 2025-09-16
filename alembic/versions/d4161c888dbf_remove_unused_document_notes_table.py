"""remove_unused_document_notes_table

Revision ID: d4161c888dbf
Revises: 759550104e16
Create Date: 2025-09-15 20:27:10.643579

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4161c888dbf'
down_revision: Union[str, Sequence[str], None] = '759550104e16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove unused document_notes table."""
    op.drop_table('document_notes')


def downgrade() -> None:
    """Recreate document_notes table."""
    op.create_table(
        'document_notes',
        sa.Column('note_id', sa.Integer, nullable=False, autoincrement=True),
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('note_type', sa.Text, nullable=False),
        sa.Column('note_text', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', sa.Text, nullable=True),
        sa.Column('note_metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('note_id'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
    )
    
    # Recreate indexes
    op.create_index('ix_document_notes_doc_id', 'document_notes', ['doc_id'])
    op.create_index('ix_document_notes_note_type', 'document_notes', ['note_type'])
