"""migrate_to_exchange_id_only

Revision ID: b2343cc60db5
Revises: 5fa221363d83
Create Date: 2025-08-25 18:07:26.435858

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2343cc60db5'
down_revision: Union[str, Sequence[str], None] = '5fa221363d83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Ensure all existing securities have exchange_id populated
    # This should already be done from the previous migration, but let's be safe
    op.execute("""
        UPDATE securities 
        SET exchange_id = e.exchange_id
        FROM exchanges e
        WHERE securities.exchange = e.code
        AND securities.exchange_id IS NULL
    """)
    
    # Make exchange_id NOT NULL since it's now our primary way to reference exchanges
    op.alter_column('securities', 'exchange_id', nullable=False)
    
    # Drop the old exchange column and its constraints
    op.drop_constraint('ck_securities_exchange', 'securities', type_='check')
    op.drop_index('idx_securities_exchange', 'securities')
    op.drop_column('securities', 'exchange')
    
    # Rename exchange_id to exchange_id for clarity (optional, but keeps naming consistent)
    # The column is already named exchange_id, so no rename needed
    
    # Add a comment to document the change
    op.execute("COMMENT ON COLUMN securities.exchange_id IS 'Foreign key to exchanges table - replaces old exchange text column'")


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate the old exchange column
    op.add_column('securities', sa.Column('exchange', sa.String(length=20), nullable=True))
    
    # Populate it from the exchanges table
    op.execute("""
        UPDATE securities 
        SET exchange = e.code
        FROM exchanges e
        WHERE securities.exchange_id = e.exchange_id
    """)
    
    # Make it NOT NULL
    op.alter_column('securities', 'exchange', nullable=False)
    
    # Recreate the check constraint
    op.execute("""
        ALTER TABLE securities ADD CONSTRAINT ck_securities_exchange 
        CHECK (exchange::text = ANY (ARRAY['NASDAQ'::character varying, 'NYSE'::character varying, 'NYSE_AM'::character varying, 'OTCQX'::character varying, 'OTCQB'::character varying]::text[]))
    """)
    
    # Recreate the index
    op.create_index('idx_securities_exchange', 'securities', ['exchange'])
    
    # Make exchange_id nullable again
    op.alter_column('securities', 'exchange_id', nullable=True)
    
    # Drop the comment
    op.execute("COMMENT ON COLUMN securities.exchange_id IS NULL")
