"""merge company migrations with study card schema

Revision ID: ea45863147eb
Revises: 20250819_company_security_link_and_view, cb8dbc1fff5f
Create Date: 2025-08-22 15:17:14.085097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea45863147eb'
down_revision: Union[str, Sequence[str], None] = ('20250818_company_securities', 'cb8dbc1fff5f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
