"""fix entity alias constraints

Revision ID: a15c0236113f
Revises: c8d9a1b2e3f4
Create Date: 2025-11-07 09:09:35.393453

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a15c0236113f'
down_revision: Union[str, None] = 'c8d9a1b2e3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old constraints
    op.drop_constraint('check_entity_type_alias', 'entity_aliases', type_='check')
    op.drop_constraint('check_alias_type', 'entity_aliases', type_='check')
    
    # Create new constraints with extended values
    op.create_check_constraint(
        'check_entity_type_alias',
        'entity_aliases',
        "entity_type IN ('company', 'drug', 'disease', 'target', 'institution', 'trial', 'publication', 'patent')"
    )
    op.create_check_constraint(
        'check_alias_type',
        'entity_aliases',
        "alias_type IN ('former_name', 'code_name', 'brand_name', 'abbreviation', 'misspelling', 'original_name', 'manual_review') OR alias_type IS NULL"
    )


def downgrade() -> None:
    # Drop new constraints
    op.drop_constraint('check_entity_type_alias', 'entity_aliases', type_='check')
    op.drop_constraint('check_alias_type', 'entity_aliases', type_='check')
    
    # Restore old constraints
    op.create_check_constraint(
        'check_entity_type_alias',
        'entity_aliases',
        "entity_type IN ('company', 'drug', 'disease', 'target', 'institution')"
    )
    op.create_check_constraint(
        'check_alias_type',
        'entity_aliases',
        "alias_type IN ('former_name', 'code_name', 'brand_name', 'abbreviation', 'misspelling') OR alias_type IS NULL"
    )

