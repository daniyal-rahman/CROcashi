"""fold_rs_scores_into_documents

Revision ID: 958cc8211a48
Revises: 92c650ab2991
Create Date: 2025-01-13 08:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '958cc8211a48'
down_revision: Union[str, Sequence[str], None] = '92c650ab2991'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fold R/S scores into documents table and remove separate doc_rs_scores table."""
    
    # 1. Add R/S scoring fields to documents table
    op.add_column('documents', sa.Column('r_score', sa.Numeric(5,4), nullable=True))
    op.add_column('documents', sa.Column('r_tier', sa.Text, nullable=True))
    op.add_column('documents', sa.Column('s_score', sa.Numeric(5,4), nullable=True))
    op.add_column('documents', sa.Column('s_tier', sa.Text, nullable=True))
    op.add_column('documents', sa.Column('r_components_jsonb', postgresql.JSONB, nullable=True))
    op.add_column('documents', sa.Column('s_components_jsonb', postgresql.JSONB, nullable=True))
    op.add_column('documents', sa.Column('rs_decided_at', sa.DateTime(timezone=True), nullable=True))
    
    # 2. Add check constraints for R/S fields
    op.create_check_constraint(
        'ck_documents_r_score_range',
        'documents',
        'r_score IS NULL OR (r_score >= 0 AND r_score <= 1)'
    )
    op.create_check_constraint(
        'ck_documents_s_score_range',
        'documents',
        's_score IS NULL OR (s_score >= 0 AND s_score <= 1)'
    )
    op.create_check_constraint(
        'ck_documents_r_tier',
        'documents',
        "r_tier IS NULL OR r_tier IN ('R0','R1','R2','R3')"
    )
    op.create_check_constraint(
        'ck_documents_s_tier',
        'documents',
        "s_tier IS NULL OR s_tier IN ('S0','S1','S2','S3')"
    )
    
    # 3. Migrate existing data from doc_rs_scores to documents
    # Note: This assumes one-to-one relationship between documents and trials
    # If a document has multiple trial scores, we'll take the most recent one
    op.execute("""
        UPDATE documents 
        SET r_score = drs."R_score",
            r_tier = drs."R_tier",
            s_score = drs."S_score",
            s_tier = drs."S_tier",
            r_components_jsonb = drs."R_components_jsonb",
            s_components_jsonb = drs."S_components_jsonb",
            rs_decided_at = drs.decided_at
        FROM (
            SELECT DISTINCT ON (doc_id) 
                doc_id, "R_score", "R_tier", "S_score", "S_tier", 
                "R_components_jsonb", "S_components_jsonb", decided_at
            FROM doc_rs_scores 
            ORDER BY doc_id, decided_at DESC
        ) drs
        WHERE documents.doc_id = drs.doc_id
    """)
    
    # 4. Add indexes for R/S fields
    op.create_index('ix_documents_r_tier', 'documents', ['r_tier'])
    op.create_index('ix_documents_s_tier', 'documents', ['s_tier'])
    op.create_index('ix_documents_rs_tiers', 'documents', ['r_tier', 's_tier'])
    op.create_index('ix_documents_rs_decided_at', 'documents', ['rs_decided_at'])
    
    # 5. Drop indexes from doc_rs_scores table
    op.drop_index('ix_doc_rs_scores_trial_tier', table_name='doc_rs_scores')
    op.drop_index('ix_doc_rs_scores_s_tier', table_name='doc_rs_scores')
    op.drop_index('ix_doc_rs_scores_r_tier', table_name='doc_rs_scores')
    op.drop_index('ix_doc_rs_scores_trial_rs', table_name='doc_rs_scores')
    
    # 6. Drop the doc_rs_scores table
    op.drop_table('doc_rs_scores')


def downgrade() -> None:
    """Reverse the migration - recreate doc_rs_scores table and move data back."""
    
    # 1. Recreate doc_rs_scores table
    op.create_table('doc_rs_scores',
        sa.Column('trial_id', sa.Integer, nullable=False),
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('R_score', sa.Numeric, nullable=False),
        sa.Column('R_tier', sa.Text, nullable=False),
        sa.Column('S_score', sa.Numeric, nullable=False),
        sa.Column('S_tier', sa.Text, nullable=False),
        sa.Column('R_components_jsonb', postgresql.JSONB, nullable=True),
        sa.Column('S_components_jsonb', postgresql.JSONB, nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('trial_id', 'doc_id'),
        sa.ForeignKeyConstraint(['trial_id'], ['trials.trial_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        sa.CheckConstraint('"R_score" >= 0 AND "R_score" <= 1', name='ck_doc_rs_scores_R_score_range'),
        sa.CheckConstraint('"S_score" >= 0 AND "S_score" <= 1', name='ck_doc_rs_scores_S_score_range'),
        sa.CheckConstraint('"R_tier"::text = ANY (ARRAY[\'R0\',\'R1\',\'R2\',\'R3\']::text[])', name='ck_doc_rs_scores_R_tier'),
        sa.CheckConstraint('"S_tier"::text = ANY (ARRAY[\'S0\',\'S1\',\'S2\',\'S3\']::text[])', name='ck_doc_rs_scores_S_tier')
    )
    
    # 2. Recreate indexes
    op.create_index('ix_doc_rs_scores_trial_rs', 'doc_rs_scores', ['trial_id', 'R_tier', 'S_tier'])
    op.create_index('ix_doc_rs_scores_r_tier', 'doc_rs_scores', ['R_tier'])
    op.create_index('ix_doc_rs_scores_s_tier', 'doc_rs_scores', ['S_tier'])
    op.create_index('ix_doc_rs_scores_trial_tier', 'doc_rs_scores', ['trial_id', 'R_tier', 'S_tier'])
    
    # 3. Migrate data back from documents to doc_rs_scores
    # Note: This assumes we can determine trial_id from document_links
    op.execute("""
        INSERT INTO doc_rs_scores (trial_id, doc_id, R_score, R_tier, S_score, S_tier, 
                                 R_components_jsonb, S_components_jsonb, decided_at)
        SELECT dl.trial_id, d.doc_id, d.r_score, d.r_tier, d.s_score, d.s_tier,
               d.r_components_jsonb, d.s_components_jsonb, d.rs_decided_at
        FROM documents d
        JOIN document_links dl ON d.doc_id = dl.doc_id
        WHERE d.r_score IS NOT NULL AND d.s_score IS NOT NULL
    """)
    
    # 4. Drop indexes from documents table
    op.drop_index('ix_documents_rs_decided_at', table_name='documents')
    op.drop_index('ix_documents_rs_tiers', table_name='documents')
    op.drop_index('ix_documents_s_tier', table_name='documents')
    op.drop_index('ix_documents_r_tier', table_name='documents')
    
    # 5. Drop check constraints from documents table
    op.drop_constraint('ck_documents_s_tier', 'documents', type_='check')
    op.drop_constraint('ck_documents_r_tier', 'documents', type_='check')
    op.drop_constraint('ck_documents_s_score_range', 'documents', type_='check')
    op.drop_constraint('ck_documents_r_score_range', 'documents', type_='check')
    
    # 6. Drop R/S columns from documents table
    op.drop_column('documents', 'rs_decided_at')
    op.drop_column('documents', 's_components_jsonb')
    op.drop_column('documents', 'r_components_jsonb')
    op.drop_column('documents', 's_tier')
    op.drop_column('documents', 's_score')
    op.drop_column('documents', 'r_tier')
    op.drop_column('documents', 'r_score')