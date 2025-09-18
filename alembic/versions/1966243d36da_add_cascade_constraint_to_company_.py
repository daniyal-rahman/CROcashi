"""add_cascade_constraint_to_company_aliases

Revision ID: 1966243d36da
Revises: b91caffec4ba
Create Date: 2025-09-17 21:26:01.404384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1966243d36da'
down_revision: Union[str, Sequence[str], None] = 'b91caffec4ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add CASCADE constraint to company_aliases.company_id."""
    # Drop the existing foreign key constraint (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'fk_company_aliases_company_id_companies'
            ) THEN
                ALTER TABLE company_aliases DROP CONSTRAINT fk_company_aliases_company_id_companies;
            END IF;
        END $$;
    """)
    
    # Add the new foreign key constraint with CASCADE
    op.create_foreign_key(
        'fk_company_aliases_company_id_companies',
        'company_aliases',
        'companies',
        ['company_id'],
        ['company_id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Remove CASCADE constraint from company_aliases.company_id."""
    # Drop the CASCADE foreign key constraint (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'fk_company_aliases_company_id_companies'
            ) THEN
                ALTER TABLE company_aliases DROP CONSTRAINT fk_company_aliases_company_id_companies;
            END IF;
        END $$;
    """)
    
    # Add back the original foreign key constraint without CASCADE
    op.create_foreign_key(
        'fk_company_aliases_company_id_companies',
        'company_aliases',
        'companies',
        ['company_id'],
        ['company_id']
    )
