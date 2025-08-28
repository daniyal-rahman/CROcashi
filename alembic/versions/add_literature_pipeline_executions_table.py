"""Add literature_pipeline_executions table

Revision ID: add_lit_pipeline_exec
Revises: ff5fabb58e9c
Create Date: 2025-08-27 20:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_lit_pipeline_exec'
down_revision = 'ff5fabb58e9c'
branch_labels = None
depends_on = None


def upgrade():
    # Create literature_pipeline_executions table
    op.create_table('literature_pipeline_executions',
        sa.Column('execution_id', sa.Text, primary_key=True),
        sa.Column('run_id', sa.Text, nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Text, nullable=False, default='running'),
        sa.Column('total_trials', sa.Integer, nullable=False, default=0),
        sa.Column('completed_trials', sa.Integer, nullable=False, default=0),
        sa.Column('total_cost', sa.Numeric(10, 6), nullable=False, default=0),
        sa.Column('execution_metadata', postgresql.JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    )
    
    # Create indexes
    op.create_index('idx_literature_pipeline_executions_run_id', 'literature_pipeline_executions', ['run_id'])
    op.create_index('idx_literature_pipeline_executions_start_time', 'literature_pipeline_executions', ['start_time'])
    op.create_index('idx_literature_pipeline_executions_status', 'literature_pipeline_executions', ['status'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_literature_pipeline_executions_status', 'literature_pipeline_executions')
    op.drop_index('idx_literature_pipeline_executions_start_time', 'literature_pipeline_executions')
    op.drop_index('idx_literature_pipeline_executions_run_id', 'literature_pipeline_executions')
    
    # Drop table
    op.drop_table('literature_pipeline_executions')
