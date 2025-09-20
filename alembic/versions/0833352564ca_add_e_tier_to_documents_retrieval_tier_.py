"""add_e_tier_to_documents_retrieval_tier_constraint

Revision ID: 0833352564ca
Revises: 5f45f25964cc
Create Date: 2025-09-20 14:58:35.470588

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0833352564ca'
down_revision: Union[str, Sequence[str], None] = '5f45f25964cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add E tier to documents retrieval_tier constraint."""
    
    # Drop the existing constraint
    op.drop_constraint('ck_documents_retrieval_tier', 'documents', type_='check')
    
    # Add the updated constraint that includes 'E' tier
    op.create_check_constraint(
        'ck_documents_retrieval_tier',
        'documents',
        "retrieval_tier::text = ANY (ARRAY['A','B','C','D','E']::text[])"
    )


def downgrade() -> None:
    """Remove E tier from documents retrieval_tier constraint."""
    
    # Drop the updated constraint
    op.drop_constraint('ck_documents_retrieval_tier', 'documents', type_='check')
    
    # Add back the original constraint without 'E' tier
    op.create_check_constraint(
        'ck_documents_retrieval_tier',
        'documents',
        "retrieval_tier::text = ANY (ARRAY['A','B','C','D']::text[])"
    )
