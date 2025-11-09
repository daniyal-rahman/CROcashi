"""add missing trial statuses

Revision ID: 99907fd43d18
Revises: a15c0236113f
Create Date: 2025-11-07 10:59:52.526366

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99907fd43d18'
down_revision: Union[str, None] = 'a15c0236113f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old constraint
    op.drop_constraint('check_trial_status', 'clinical_trials', type_='check')
    
    # Create new constraint with additional statuses
    op.create_check_constraint(
        'check_trial_status',
        'clinical_trials',
        "status IN ('recruiting', 'active', 'completed', 'terminated', 'suspended', 'withdrawn', 'unknown', 'enrolling_by_invitation', 'active_not_recruiting', 'not_yet_recruiting') OR status IS NULL"
    )


def downgrade() -> None:
    # Drop new constraint
    op.drop_constraint('check_trial_status', 'clinical_trials', type_='check')
    
    # Restore old constraint
    op.create_check_constraint(
        'check_trial_status',
        'clinical_trials',
        "status IN ('recruiting', 'active', 'completed', 'terminated', 'suspended', 'withdrawn') OR status IS NULL"
    )

