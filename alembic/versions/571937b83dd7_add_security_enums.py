"""add_security_enums

Revision ID: 571937b83dd7
Revises: fe02bb9a421d
Create Date: 2025-08-25 18:04:58.545974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '571937b83dd7'
down_revision: Union[str, Sequence[str], None] = 'fe02bb9a421d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create security_type enum
    op.execute("CREATE TYPE security_type AS ENUM ('common', 'preferred', 'warrant', 'option', 'bond', 'etf', 'adr')")
    
    # Create security_status enum
    op.execute("CREATE TYPE security_status AS ENUM ('active', 'delisted', 'suspended', 'expired')")
    
    # Drop defaults first, then alter types, then set defaults again
    op.execute("ALTER TABLE securities ALTER COLUMN type DROP DEFAULT")
    op.execute("ALTER TABLE securities ALTER COLUMN status DROP DEFAULT")
    
    # Alter securities table to use the new enums
    op.execute("ALTER TABLE securities ALTER COLUMN type TYPE security_type USING type::security_type")
    op.execute("ALTER TABLE securities ALTER COLUMN status TYPE security_status USING status::security_status")
    
    # Set defaults again
    op.execute("ALTER TABLE securities ALTER COLUMN type SET DEFAULT 'common'::security_type")
    op.execute("ALTER TABLE securities ALTER COLUMN status SET DEFAULT 'active'::security_status")


def downgrade() -> None:
    """Downgrade schema."""
    # Alter securities table back to varchar
    op.execute("ALTER TABLE securities ALTER COLUMN type TYPE VARCHAR(20) USING type::text")
    op.execute("ALTER TABLE securities ALTER COLUMN status TYPE VARCHAR(20) USING status::text")
    
    # Drop the enums
    op.execute("DROP TYPE security_status")
    op.execute("DROP TYPE security_type")
