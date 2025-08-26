"""update_securities_table_schema

Revision ID: 669b4722606d
Revises: b27978a07448
Create Date: 2025-08-25 18:03:41.695003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '669b4722606d'
down_revision: Union[str, Sequence[str], None] = 'b27978a07448'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add missing columns to securities table
    op.add_column('securities', sa.Column('ticker_norm', sa.Text(), nullable=True))
    op.add_column('securities', sa.Column('exchange_id', sa.Integer(), nullable=True))
    op.add_column('securities', sa.Column('status', sa.String(length=20), nullable=True, server_default='active'))
    op.add_column('securities', sa.Column('effective_range', sa.dialects.postgresql.DATERANGE(), nullable=True))
    op.add_column('securities', sa.Column('type', sa.String(length=20), nullable=True, server_default='common'))
    op.add_column('securities', sa.Column('currency', sa.String(length=3), nullable=True, server_default='USD'))
    op.add_column('securities', sa.Column('figi', sa.String(length=12), nullable=True))
    op.add_column('securities', sa.Column('is_primary_listing', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('securities', sa.Column('metadata', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('securities', sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=True, server_default=sa.text('now()')))
    op.add_column('securities', sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=True, server_default=sa.text('now()')))
    
    # Create foreign key constraint for exchange_id
    op.create_foreign_key('fk_securities_exchange_id', 'securities', 'exchanges', ['exchange_id'], ['exchange_id'])
    
    # Create index on ticker_norm
    op.create_index('idx_securities_ticker_norm', 'securities', ['ticker_norm'])
    
    # Create index on effective_range
    op.create_index('idx_securities_effective_range', 'securities', ['effective_range'])
    
    # Update existing rows to set default values
    op.execute("""
        UPDATE securities 
        SET ticker_norm = UPPER(ticker),
            status = 'active',
            type = 'common',
            currency = 'USD',
            is_primary_listing = true,
            created_at = NOW(),
            updated_at = NOW()
        WHERE ticker_norm IS NULL
    """)
    
    # Map existing exchange values to exchange_id
    op.execute("""
        UPDATE securities 
        SET exchange_id = e.exchange_id
        FROM exchanges e
        WHERE securities.exchange = e.code
    """)
    
    # Set effective_range for existing active securities
    op.execute("""
        UPDATE securities 
        SET effective_range = daterange('1900-01-01'::date, NULL, '[)')
        WHERE effective_range IS NULL AND active = true
    """)
    
    # Set effective_range for existing inactive securities
    op.execute("""
        UPDATE securities 
        SET effective_range = daterange('1900-01-01'::date, '1900-01-01'::date, '[)')
        WHERE effective_range IS NULL AND active = false
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_securities_effective_range', 'securities')
    op.drop_index('idx_securities_ticker_norm', 'securities')
    
    # Drop foreign key constraint
    op.drop_constraint('fk_securities_exchange_id', 'securities', type_='foreignkey')
    
    # Drop added columns
    op.drop_column('securities', 'updated_at')
    op.drop_column('securities', 'created_at')
    op.drop_column('securities', 'metadata')
    op.drop_column('securities', 'is_primary_listing')
    op.drop_column('securities', 'figi')
    op.drop_column('securities', 'currency')
    op.drop_column('securities', 'type')
    op.drop_column('securities', 'effective_range')
    op.drop_column('securities', 'status')
    op.drop_column('securities', 'exchange_id')
    op.drop_column('securities', 'ticker_norm')
