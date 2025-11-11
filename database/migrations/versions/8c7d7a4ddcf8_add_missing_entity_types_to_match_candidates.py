"""add missing entity types to entity_match_candidates constraint

Revision ID: 8c7d7a4ddcf8
Revises: f1a2b3c4d5e6
Create Date: 2025-11-09 21:36:17.822849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8c7d7a4ddcf8'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old constraint
    op.drop_constraint('check_candidate_entity_type', 'entity_match_candidates', type_='check')
    
    # Add new constraint with all entity types
    op.create_check_constraint(
        'check_candidate_entity_type',
        'entity_match_candidates',
        "entity_type IN ('company', 'drug', 'disease', 'target', 'trial', 'publication', 'institution', 'mechanism', 'patent', 'regulatory_event', 'sec_filing', 'conference_presentation')"
    )


def downgrade() -> None:
    # Drop the new constraint
    op.drop_constraint('check_candidate_entity_type', 'entity_match_candidates', type_='check')
    
    # Restore old constraint
    op.create_check_constraint(
        'check_candidate_entity_type',
        'entity_match_candidates',
        "entity_type IN ('company', 'drug', 'disease', 'target', 'trial', 'publication', 'institution')"
    )


