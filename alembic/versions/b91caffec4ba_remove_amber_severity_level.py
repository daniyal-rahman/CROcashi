"""remove_amber_severity_level

Revision ID: b91caffec4ba
Revises: bc59812a5ceb
Create Date: 2025-09-17 00:54:07.059861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b91caffec4ba'
down_revision: Union[str, Sequence[str], None] = 'bc59812a5ceb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Update severity constraint from 0-3 to 0-2 range
    op.drop_constraint('ck_severity_range', 'pattern_detections', type_='check')
    op.create_check_constraint(
        'ck_severity_range',
        'pattern_detections',
        'severity >= 0 AND severity <= 2'
    )
    
    # Update any existing AMBER values (severity=2) to YELLOW (severity=1)
    # This handles the case where AMBER was mapped to value 2
    op.execute("""
        UPDATE pattern_detections 
        SET severity = 1 
        WHERE severity = 2
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert severity constraint back to 0-3 range
    op.drop_constraint('ck_severity_range', 'pattern_detections', type_='check')
    op.create_check_constraint(
        'ck_severity_range',
        'pattern_detections',
        'severity >= 0 AND severity <= 3'
    )
    
    # Note: We don't revert the data changes as we can't distinguish
    # between original YELLOW (1) and converted AMBER (2) values
