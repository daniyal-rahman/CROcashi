"""remove_lr_tables_and_document_text_pages

Revision ID: 727232fd50ae
Revises: 7d530c0cf176
Create Date: 2025-09-15 19:14:10.656298

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '727232fd50ae'
down_revision: Union[str, Sequence[str], None] = '7d530c0cf176'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove lr_tables and document_text_pages tables."""
    # Drop document_text_pages table first (has foreign key to documents)
    op.drop_table('document_text_pages')
    
    # Drop lr_tables table
    op.drop_table('lr_tables')


def downgrade() -> None:
    """Recreate lr_tables and document_text_pages tables."""
    from sqlalchemy.dialects import postgresql as psql
    
    # Recreate lr_tables table
    op.create_table(
        'lr_tables',
        sa.Column('lr_id', sa.BigInteger, nullable=False, autoincrement=True),
        sa.Column('scope', sa.String(length=10), nullable=False),
        sa.Column('id_code', sa.String(length=8), nullable=False),
        sa.Column('universe_tag', sa.Text, nullable=False),
        sa.Column('lr_value', sa.Numeric(10, 6), nullable=False),
        sa.Column('ci_low', sa.Numeric(10, 6), nullable=True),
        sa.Column('ci_high', sa.Numeric(10, 6), nullable=True),
        sa.Column('effective_from', sa.Date, nullable=False),
        sa.Column('effective_to', sa.Date, nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('lr_id', name='pk_lr_tables'),
    )
    
    # Add constraints for lr_tables
    op.create_check_constraint('ck_lr_tables_scope', 'lr_tables', "(scope IN ('gate','signal'))")
    op.create_check_constraint('ck_lr_tables_id_code_matches_scope', 'lr_tables', 
                              "((scope = 'gate' AND id_code IN ('G1','G2','G3','G4')) OR (scope = 'signal' AND id_code IN ('S1','S2','S3','S4','S5','S6','S7','S8','S9')))")
    op.create_check_constraint('ck_lr_tables_date_order', 'lr_tables', "(effective_to IS NULL OR effective_from <= effective_to)")
    op.create_index('idx_lr_tables_id_universe_effective', 'lr_tables', ['id_code', 'universe_tag', 'effective_from'])
    
    # Recreate document_text_pages table
    op.create_table(
        'document_text_pages',
        sa.Column('doc_id', sa.Integer, nullable=False),
        sa.Column('page_no', sa.Integer, nullable=False),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('char_count', sa.Integer, nullable=True),
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('doc_id', 'page_no'),
    )
