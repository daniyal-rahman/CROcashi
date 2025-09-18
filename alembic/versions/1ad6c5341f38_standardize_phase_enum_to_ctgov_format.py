"""standardize_phase_enum_to_ctgov_format

Revision ID: 1ad6c5341f38
Revises: 250ab25cf2a6
Create Date: 2025-09-17 21:57:42.214498

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ad6c5341f38'
down_revision: Union[str, Sequence[str], None] = '250ab25cf2a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Standardize phase enum to CT.gov format."""
    # Drop old enum
    op.execute("DROP TYPE IF EXISTS phase_enum CASCADE")
    
    # Create new enum with CT.gov format
    op.execute("""
        CREATE TYPE phase_enum AS ENUM (
            'PHASE1', 'PHASE2', 'PHASE3', 'PHASE4',
            'PHASE2_PHASE3', 'PHASE1_PHASE2', 'PHASE3_PHASE4',
            'EARLY_PHASE1'
        )
    """)
    
    # Update existing data in trials table
    op.execute("""
        UPDATE trials SET phase = CASE
            WHEN phase = 'P1' THEN 'PHASE1'
            WHEN phase = 'P2' THEN 'PHASE2'
            WHEN phase = 'P2B' THEN 'PHASE2'
            WHEN phase = 'P2_3' THEN 'PHASE2_PHASE3'
            WHEN phase = 'P3' THEN 'PHASE3'
            WHEN phase = 'P4' THEN 'PHASE4'
            ELSE 'UNKNOWN'
        END
    """)
    
    # Update column to use new enum type
    op.alter_column('trials', 'phase', 
                   type_=sa.Enum('PHASE1', 'PHASE2', 'PHASE3', 'PHASE4', 
                                'PHASE2_PHASE3', 'PHASE1_PHASE2', 'PHASE3_PHASE4', 
                                'EARLY_PHASE1', name='phase_enum'),
                   existing_type=sa.String(8))


def downgrade() -> None:
    """Revert phase enum to old format."""
    # Drop new enum
    op.execute("DROP TYPE IF EXISTS phase_enum CASCADE")
    
    # Create old enum
    op.execute("""
        CREATE TYPE phase_enum AS ENUM (
            'P2', 'P2B', 'P2_3', 'P3'
        )
    """)
    
    # Revert data in trials table
    op.execute("""
        UPDATE trials SET phase = CASE
            WHEN phase = 'PHASE1' THEN 'P2'  -- Map PHASE1 to P2 (closest)
            WHEN phase = 'PHASE2' THEN 'P2'
            WHEN phase = 'PHASE3' THEN 'P3'
            WHEN phase = 'PHASE4' THEN 'P3'  -- Map PHASE4 to P3 (closest)
            WHEN phase = 'PHASE2_PHASE3' THEN 'P2_3'
            WHEN phase = 'PHASE1_PHASE2' THEN 'P2'
            WHEN phase = 'PHASE3_PHASE4' THEN 'P3'
            WHEN phase = 'EARLY_PHASE1' THEN 'P2'
            ELSE 'P2'
        END
    """)
    
    # Revert column to use old enum type
    op.alter_column('trials', 'phase', 
                   type_=sa.Enum('P2', 'P2B', 'P2_3', 'P3', name='phase_enum'),
                   existing_type=sa.Enum('PHASE1', 'PHASE2', 'PHASE3', 'PHASE4', 
                                        'PHASE2_PHASE3', 'PHASE1_PHASE2', 'PHASE3_PHASE4', 
                                        'EARLY_PHASE1', name='phase_enum'))
