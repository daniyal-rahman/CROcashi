"""refactor_factsheet_schema_jsonb_sections_provenance

Revision ID: 903237fab6ce
Revises: 0833352564ca
Create Date: 2025-09-23 13:37:08.058570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '903237fab6ce'
down_revision: Union[str, Sequence[str], None] = '0833352564ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns to factsheets table
    op.add_column('factsheets', sa.Column('study_type', sa.String(32), nullable=True))
    op.add_column('factsheets', sa.Column('factsheet_sections', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('factsheets', sa.Column('provenance', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('factsheets', sa.Column('normalized_facts', sa.dialects.postgresql.JSONB(), nullable=True))
    
    # Add check constraint for study_type
    op.create_check_constraint(
        'ck_factsheets_study_type',
        'factsheets',
        "study_type IN ('clinical_trial', 'preclinical', 'review', 'case_study', 'other')"
    )
    
    # Add index for JSONB queries
    op.create_index('idx_factsheets_sections_gin', 'factsheets', ['factsheet_sections'], postgresql_using='gin')
    op.create_index('idx_factsheets_provenance_gin', 'factsheets', ['provenance'], postgresql_using='gin')
    op.create_index('idx_factsheets_normalized_facts_gin', 'factsheets', ['normalized_facts'], postgresql_using='gin')
    op.create_index('idx_factsheets_study_type', 'factsheets', ['study_type'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_factsheets_study_type', 'factsheets')
    op.drop_index('idx_factsheets_normalized_facts_gin', 'factsheets')
    op.drop_index('idx_factsheets_provenance_gin', 'factsheets')
    op.drop_index('idx_factsheets_sections_gin', 'factsheets')
    
    # Drop check constraint
    op.drop_constraint('ck_factsheets_study_type', 'factsheets', type_='check')
    
    # Drop columns
    op.drop_column('factsheets', 'normalized_facts')
    op.drop_column('factsheets', 'provenance')
    op.drop_column('factsheets', 'factsheet_sections')
    op.drop_column('factsheets', 'study_type')
