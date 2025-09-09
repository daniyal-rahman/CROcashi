"""add_u1_discovery_stage_constraint

Revision ID: 2247826a03d9
Revises: 8586ac67f466
Create Date: 2025-09-08 14:03:16.546177

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2247826a03d9'
down_revision: Union[str, Sequence[str], None] = '8586ac67f466'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop the old constraint
    op.drop_constraint('ck_trial_doc_candidates_stage', 'trial_doc_candidates', type_='check')
    
    # Add the new constraint with U1_discovery stage
    op.create_check_constraint(
        'ck_trial_doc_candidates_stage',
        'trial_doc_candidates',
        "stage::text = ANY (ARRAY['U0_meta','U1_discovery','U1_abstract','OA_fulltext']::text[])"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the new constraint
    op.drop_constraint('ck_trial_doc_candidates_stage', 'trial_doc_candidates', type_='check')
    
    # Restore the old constraint without U1_discovery stage
    op.create_check_constraint(
        'ck_trial_doc_candidates_stage',
        'trial_doc_candidates',
        "stage::text = ANY (ARRAY['U0_meta','U1_abstract','OA_fulltext']::text[])"
    )
