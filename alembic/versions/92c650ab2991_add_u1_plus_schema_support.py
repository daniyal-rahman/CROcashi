"""add_u1_plus_schema_support

Revision ID: 92c650ab2991
Revises: afc070443f13
Create Date: 2025-09-08 14:22:23.745323

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92c650ab2991'
down_revision: Union[str, Sequence[str], None] = 'afc070443f13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add UNIQUE constraint on documents.pmid for U1+ support
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_pmid 
        ON documents(pmid) 
        WHERE pmid IS NOT NULL
        """
    )
    
    # Update documents status constraint to include U1+ statuses
    op.drop_constraint('ck_documents_status', 'documents', type_='check')
    op.create_check_constraint(
        'ck_documents_status',
        'documents',
        "status::text = ANY (ARRAY['discovered','abstracted','scored','fulltexted','fetched','parsed','linked','failed']::text[])"
    )
    
    # Add indexes for U1+ performance (only if they don't exist)
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_status_pmid ON documents(status, pmid)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_trial_doc_candidates_trial_stage ON trial_doc_candidates(trial_id, stage)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_doc_rs_scores_trial_tier ON doc_rs_scores(trial_id, \"R_tier\", \"S_tier\")")


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('ix_doc_rs_scores_trial_tier', table_name='doc_rs_scores')
    op.drop_index('ix_trial_doc_candidates_trial_stage', table_name='trial_doc_candidates')
    op.drop_index('ix_documents_status_pmid', table_name='documents')
    
    # Restore original status constraint
    op.drop_constraint('ck_documents_status', 'documents', type_='check')
    op.create_check_constraint(
        'ck_documents_status',
        'documents',
        "status::text = ANY (ARRAY['discovered','fetched','parsed','linked','failed']::text[])"
    )
    
    # Drop UNIQUE index
    op.execute("DROP INDEX IF EXISTS uq_documents_pmid")
