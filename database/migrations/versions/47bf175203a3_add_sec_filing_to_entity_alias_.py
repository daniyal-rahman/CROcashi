"""add sec_filing to entity alias constraint

Revision ID: 47bf175203a3
Revises: a15c0236113f
Create Date: 2025-11-07 17:53:30.642644

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '47bf175203a3'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the old constraint
    op.drop_constraint('check_entity_type_alias', 'entity_aliases', type_='check')
    
    # Add new constraint that includes 'sec_filing'
    op.create_check_constraint(
        'check_entity_type_alias',
        'entity_aliases',
        "entity_type IN ('company', 'drug', 'disease', 'target', 'institution', 'trial', 'publication', 'patent', 'sec_filing')"
    )


def downgrade():
    # Drop the new constraint
    op.drop_constraint('check_entity_type_alias', 'entity_aliases', type_='check')
    
    # Restore the old constraint without 'sec_filing'
    op.create_check_constraint(
        'check_entity_type_alias',
        'entity_aliases',
        "entity_type IN ('company', 'drug', 'disease', 'target', 'institution', 'trial', 'publication', 'patent')"
    )
