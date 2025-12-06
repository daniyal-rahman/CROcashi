"""add trial status history

Revision ID: d4e5f6a7b8c9
Revises: 99907fd43d18
Create Date: 2025-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = '99907fd43d18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create trial_status_history table
    op.create_table(
        'trial_status_history',
        sa.Column('history_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('trial_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('status_date', sa.Date, nullable=False),
        sa.Column('source', sa.String(200), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['trial_id'], ['clinical_trials.trial_id'], ondelete='CASCADE'),
        sa.CheckConstraint(
            "status IN ('recruiting', 'active', 'completed', 'terminated', 'suspended', 'withdrawn', 'unknown', 'enrolling_by_invitation', 'active_not_recruiting', 'not_yet_recruiting') OR status IS NOT NULL",
            name='check_status_history_status'
        ),
    )
    
    # Create indexes
    op.create_index('ix_trial_status_history_history_id', 'trial_status_history', ['history_id'])
    op.create_index('ix_trial_status_history_trial_id', 'trial_status_history', ['trial_id'])
    op.create_index('ix_trial_status_history_status', 'trial_status_history', ['status'])
    op.create_index('ix_trial_status_history_status_date', 'trial_status_history', ['status_date'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_trial_status_history_status_date', table_name='trial_status_history')
    op.drop_index('ix_trial_status_history_status', table_name='trial_status_history')
    op.drop_index('ix_trial_status_history_trial_id', table_name='trial_status_history')
    op.drop_index('ix_trial_status_history_history_id', table_name='trial_status_history')
    
    # Drop table
    op.drop_table('trial_status_history')

