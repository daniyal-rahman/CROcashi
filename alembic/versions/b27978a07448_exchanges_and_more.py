"""exchanges and more

Revision ID: b27978a07448
Revises: 57f62acd287e
Create Date: 2025-08-25 17:57:15.859136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b27978a07448'
down_revision: Union[str, Sequence[str], None] = '57f62acd287e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create exchanges table
    op.create_table(
        'exchanges',
        sa.Column('exchange_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('is_allowed', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.PrimaryKeyConstraint('exchange_id'),
        sa.UniqueConstraint('code')
    )
    
    # Insert default exchange data
    op.execute("""
        INSERT INTO exchanges (code, name, is_allowed) VALUES 
        ('NASDAQ', 'NASDAQ', true),
        ('NYSE', 'New York Stock Exchange', true),
        ('NYSE_AM', 'NYSE American', true),
        ('OTCQX', 'OTCQX', true),
        ('OTCQB', 'OTCQB', true)
    """)
    
    # Add any other necessary schema changes here
    # For example, if securities table needs exchange_id column:
    # op.add_column('securities', sa.Column('exchange_id', sa.Integer(), nullable=True))
    # op.create_foreign_key('fk_securities_exchange', 'securities', 'exchanges', ['exchange_id'], ['exchange_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop exchanges table
    op.drop_table('exchanges')
    
    # Remove any other columns/tables added in upgrade
    # For example:
    # op.drop_constraint('fk_securities_exchange', 'securities', type_='foreignkey')
    # op.drop_column('securities', 'exchange_id')
