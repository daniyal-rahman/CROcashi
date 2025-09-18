"""fix_naming_conventions_and_constraints

Revision ID: 8daa81386878
Revises: 1ad6c5341f38
Create Date: 2025-09-17 22:56:41.732529

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8daa81386878'
down_revision: Union[str, Sequence[str], None] = '1ad6c5341f38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix naming conventions and constraints."""
    
    # 1. Add missing check constraint for company_aliases.alias_type (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'ck_company_aliases_alias_type_valid'
            ) THEN
                ALTER TABLE company_aliases 
                ADD CONSTRAINT ck_company_aliases_alias_type_valid 
                CHECK (alias_type IN ('legal','aka','former_name','short','subsidiary','brand','domain'));
            END IF;
        END $$;
    """)
    
    # 2. Fix study_cards.doc_id data type and rename id to study_card_id (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            -- First fix the doc_id data type if it's String
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'study_cards' 
                AND column_name = 'doc_id' 
                AND data_type = 'character varying'
            ) THEN
                -- Convert doc_id from String to Integer
                ALTER TABLE study_cards ALTER COLUMN doc_id TYPE INTEGER USING doc_id::INTEGER;
            END IF;
            
            -- Then rename id to study_card_id
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'study_cards' AND column_name = 'id'
            ) THEN
                ALTER TABLE study_cards RENAME COLUMN id TO study_card_id;
            END IF;
        END $$;
    """)
    
    # 3. Fix factsheets.doc_id data type and rename id to factsheet_id (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            -- First fix the doc_id data type if it's String
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'factsheets' 
                AND column_name = 'doc_id' 
                AND data_type = 'character varying'
            ) THEN
                -- Convert doc_id from String to Integer
                ALTER TABLE factsheets ALTER COLUMN doc_id TYPE INTEGER USING doc_id::INTEGER;
            END IF;
            
            -- Then rename id to factsheet_id
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'factsheets' AND column_name = 'id'
            ) THEN
                ALTER TABLE factsheets RENAME COLUMN id TO factsheet_id;
            END IF;
        END $$;
    """)
    
    # 4. Remove duplicate cik field from securities table (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'securities' AND column_name = 'cik'
            ) THEN
                ALTER TABLE securities DROP COLUMN cik;
            END IF;
        END $$;
    """)
    
    # 5. Update document_citations table structure for outbound citations (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            -- Drop existing indexes first
            DROP INDEX IF EXISTS idx_document_citations_doc_id;
            DROP INDEX IF EXISTS idx_document_citations_cited_doi;
            DROP INDEX IF EXISTS idx_document_citations_cited_pmid;
            DROP INDEX IF EXISTS idx_document_citations_cited_pmcid;
            
            -- Drop the existing table if it exists
            DROP TABLE IF EXISTS document_citations CASCADE;
        END $$;
    """)
    
    op.create_table(
        'document_citations',
        sa.Column('citation_id', sa.Integer, nullable=False, autoincrement=True, primary_key=True),
        sa.Column('doc_id', sa.Integer, nullable=False),  # Document that cites
        sa.Column('cited_doi', sa.Text, nullable=True),
        sa.Column('cited_pmid', sa.Text, nullable=True),
        sa.Column('cited_pmcid', sa.Text, nullable=True),
        sa.Column('cited_nct_id', sa.Text, nullable=True),
        sa.Column('cited_title', sa.Text, nullable=True),
        sa.Column('cited_journal', sa.Text, nullable=True),
        sa.Column('cited_volume', sa.Text, nullable=True),
        sa.Column('cited_issue', sa.Text, nullable=True),
        sa.Column('cited_pages', sa.Text, nullable=True),
        sa.Column('cited_article_type', sa.Text, nullable=True),
        sa.Column('cited_pub_year', sa.Integer, nullable=True),
        sa.Column('citation_context', sa.Text, nullable=True),  # How it's cited
        sa.Column('citation_type', sa.Text, nullable=True),  # reference, background, etc.
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        # Foreign key
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
    )
    
    # Create indexes for the new document_citations table (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_document_citations_doc_id'
            ) THEN
                CREATE INDEX idx_document_citations_doc_id ON document_citations (doc_id);
            END IF;
            
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_document_citations_cited_doi'
            ) THEN
                CREATE INDEX idx_document_citations_cited_doi ON document_citations (cited_doi);
            END IF;
            
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_document_citations_cited_pmid'
            ) THEN
                CREATE INDEX idx_document_citations_cited_pmid ON document_citations (cited_pmid);
            END IF;
            
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_document_citations_cited_pmcid'
            ) THEN
                CREATE INDEX idx_document_citations_cited_pmcid ON document_citations (cited_pmcid);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert naming convention fixes."""
    
    # 1. Remove check constraint for company_aliases.alias_type (indempotent)
    op.execute("ALTER TABLE company_aliases DROP CONSTRAINT IF EXISTS ck_company_aliases_alias_type_valid")
    
    # 2. Rename study_card_id back to id (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'study_cards' AND column_name = 'study_card_id'
            ) THEN
                ALTER TABLE study_cards RENAME COLUMN study_card_id TO id;
            END IF;
        END $$;
    """)
    
    # 3. Rename factsheet_id back to id (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'factsheets' AND column_name = 'factsheet_id'
            ) THEN
                ALTER TABLE factsheets RENAME COLUMN factsheet_id TO id;
            END IF;
        END $$;
    """)
    
    # 4. Add back cik field to securities table (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'securities' AND column_name = 'cik'
            ) THEN
                ALTER TABLE securities ADD COLUMN cik TEXT;
            END IF;
        END $$;
    """)
    
    # 5. Revert document_citations table structure (indempotent)
    op.execute("""
        DO $$ 
        BEGIN
            -- Drop existing indexes first
            DROP INDEX IF EXISTS idx_document_citations_doc_id;
            DROP INDEX IF EXISTS idx_document_citations_cited_doi;
            DROP INDEX IF EXISTS idx_document_citations_cited_pmid;
            DROP INDEX IF EXISTS idx_document_citations_cited_pmcid;
            
            -- Drop the existing table if it exists
            DROP TABLE IF EXISTS document_citations CASCADE;
        END $$;
    """)
    
    # Recreate the old structure (1:1 with documents)
    op.create_table(
        'document_citations',
        sa.Column('doc_id', sa.Integer, nullable=False, primary_key=True),
        sa.Column('doi', sa.Text, nullable=True),
        sa.Column('pmid', sa.Text, nullable=True),
        sa.Column('pmcid', sa.Text, nullable=True),
        sa.Column('nct_id', sa.Text, nullable=True),
        sa.Column('journal', sa.Text, nullable=True),
        sa.Column('volume', sa.Text, nullable=True),
        sa.Column('issue', sa.Text, nullable=True),
        sa.Column('pages', sa.Text, nullable=True),
        sa.Column('article_type', sa.Text, nullable=True),
        sa.Column('pub_year', sa.Integer, nullable=True),
        sa.Column('mesh_jsonb', sa.JSON, nullable=True),
        sa.Column('substances_jsonb', sa.JSON, nullable=True),
        
        # Foreign key
        sa.ForeignKeyConstraint(['doc_id'], ['documents.doc_id'], ondelete='CASCADE'),
    )
