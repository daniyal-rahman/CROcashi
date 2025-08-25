"""add date tracking to trials

Revision ID: 583de950b814
Revises: 3a0381c42074
Create Date: 2025-08-24 22:32:05.367644

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '583de950b814'
down_revision: Union[str, Sequence[str], None] = '3a0381c42074'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.add_column('trials',
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False)
    )
    op.add_column('trials',
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False)
    )
    # Drop server default on created_at after backfilling
    op.alter_column('trials', 'created_at', server_default=None)

def downgrade():
    op.drop_column('trials', 'updated_at')
    op.drop_column('trials', 'created_at')
