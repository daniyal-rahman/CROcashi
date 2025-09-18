"""add_foreign_key_constraints_to_study_cards

Revision ID: 250ab25cf2a6
Revises: 1966243d36da
Create Date: 2025-09-17 21:28:18.294505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '250ab25cf2a6'
down_revision: Union[str, Sequence[str], None] = '1966243d36da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add foreign key constraints to study_cards and factsheets tables."""
    # First fix data types for doc_id columns
    op.execute("""
        DO $$ 
        BEGIN
            -- Fix study_cards.doc_id data type if it's String
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'study_cards' 
                AND column_name = 'doc_id' 
                AND data_type = 'character varying'
            ) THEN
                ALTER TABLE study_cards ALTER COLUMN doc_id TYPE INTEGER USING doc_id::INTEGER;
            END IF;
            
            -- Fix factsheets.doc_id data type if it's String
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'factsheets' 
                AND column_name = 'doc_id' 
                AND data_type = 'character varying'
            ) THEN
                ALTER TABLE factsheets ALTER COLUMN doc_id TYPE INTEGER USING doc_id::INTEGER;
            END IF;
        END $$;
    """)
    
    # Add foreign key constraint for study_cards.doc_id -> documents.doc_id (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'fk_study_cards_doc_id_documents'
            ) THEN
                ALTER TABLE study_cards 
                ADD CONSTRAINT fk_study_cards_doc_id_documents 
                FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)
    
    # Add foreign key constraint for factsheets.doc_id -> documents.doc_id (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'fk_factsheets_doc_id_documents'
            ) THEN
                ALTER TABLE factsheets 
                ADD CONSTRAINT fk_factsheets_doc_id_documents 
                FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Remove foreign key constraints from study_cards and factsheets tables."""
    # Drop foreign key constraint for study_cards.doc_id (indempotent)
    op.execute("ALTER TABLE study_cards DROP CONSTRAINT IF EXISTS fk_study_cards_doc_id_documents")
    
    # Drop foreign key constraint for factsheets.doc_id (indempotent)
    op.execute("ALTER TABLE factsheets DROP CONSTRAINT IF EXISTS fk_factsheets_doc_id_documents")
