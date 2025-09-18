"""add_foreign_key_constraints_to_study_cards

Revision ID: 250ab25cf2a6
Revises: 1966243d36da
Create Date: 2025-09-17 21:28:18.294505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '250ab25cf2a6'
down_revision: Union[str, Sequence[str], None] = '1966243d36da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add foreign key constraints to study_cards and factsheets tables."""
    # Add foreign key constraint for study_cards.doc_id -> documents.doc_id
    op.create_foreign_key(
        'fk_study_cards_doc_id_documents',
        'study_cards',
        'documents',
        ['doc_id'],
        ['doc_id'],
        ondelete='CASCADE'
    )
    
    # Add foreign key constraint for factsheets.doc_id -> documents.doc_id
    op.create_foreign_key(
        'fk_factsheets_doc_id_documents',
        'factsheets',
        'documents',
        ['doc_id'],
        ['doc_id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Remove foreign key constraints from study_cards and factsheets tables."""
    # Drop foreign key constraint for study_cards.doc_id
    op.drop_constraint('fk_study_cards_doc_id_documents', 'study_cards', type_='foreignkey')
    
    # Drop foreign key constraint for factsheets.doc_id
    op.drop_constraint('fk_factsheets_doc_id_documents', 'factsheets', type_='foreignkey')
