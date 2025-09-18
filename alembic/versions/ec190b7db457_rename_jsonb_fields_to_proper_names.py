"""rename jsonb fields to proper names

Revision ID: ec190b7db457
Revises: 8daa81386878
Create Date: 2024-12-19 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ec190b7db457'
down_revision = '8daa81386878'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename all JSONB fields to proper names without _jsonb suffix."""
    
    # 1. Rename assets.names_jsonb to assets.names
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'assets' AND column_name = 'names_jsonb'
            ) THEN
                ALTER TABLE assets RENAME COLUMN names_jsonb TO names;
            END IF;
        END $$;
    """)
    
    # 2. Rename trial_versions.raw_jsonb to trial_versions.raw_data
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trial_versions' AND column_name = 'raw_jsonb'
            ) THEN
                ALTER TABLE trial_versions RENAME COLUMN raw_jsonb TO raw_data;
            END IF;
        END $$;
    """)
    
    # 3. Rename trial_versions.changes_jsonb to trial_versions.changes
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trial_versions' AND column_name = 'changes_jsonb'
            ) THEN
                ALTER TABLE trial_versions RENAME COLUMN changes_jsonb TO changes;
            END IF;
        END $$;
    """)
    
    # 4. Rename trial_versions.metadata_jsonb to trial_versions.meta
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trial_versions' AND column_name = 'metadata_jsonb'
            ) THEN
                ALTER TABLE trial_versions RENAME COLUMN metadata_jsonb TO meta;
            END IF;
        END $$;
    """)
    
    # 5. Rename studies.extracted_jsonb to studies.extracted_data
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'studies' AND column_name = 'extracted_jsonb'
            ) THEN
                ALTER TABLE studies RENAME COLUMN extracted_jsonb TO extracted_data;
            END IF;
        END $$;
    """)
    
    # 6. Rename patents.links_jsonb to patents.links
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'patents' AND column_name = 'links_jsonb'
            ) THEN
                ALTER TABLE patents RENAME COLUMN links_jsonb TO links;
            END IF;
        END $$;
    """)
    
    # 7. Rename signals.metadata_jsonb to signals.meta
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'signals' AND column_name = 'metadata_jsonb'
            ) THEN
                ALTER TABLE signals RENAME COLUMN metadata_jsonb TO meta;
            END IF;
        END $$;
    """)
    
    # 8. Rename signal_evidence.metadata_jsonb to signal_evidence.meta
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'signal_evidence' AND column_name = 'metadata_jsonb'
            ) THEN
                ALTER TABLE signal_evidence RENAME COLUMN metadata_jsonb TO meta;
            END IF;
        END $$;
    """)
    
    # 9. Rename documents.r_components_jsonb to documents.r_components
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'documents' AND column_name = 'r_components_jsonb'
            ) THEN
                ALTER TABLE documents RENAME COLUMN r_components_jsonb TO r_components;
            END IF;
        END $$;
    """)
    
    # 10. Rename documents.s_components_jsonb to documents.s_components
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'documents' AND column_name = 's_components_jsonb'
            ) THEN
                ALTER TABLE documents RENAME COLUMN s_components_jsonb TO s_components;
            END IF;
        END $$;
    """)
    
    # 11. Rename document_tables.table_jsonb to document_tables.table_data
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'document_tables' AND column_name = 'table_jsonb'
            ) THEN
                ALTER TABLE document_tables RENAME COLUMN table_jsonb TO table_data;
            END IF;
        END $$;
    """)
    
    # 12. Rename document_links.evidence_json to document_links.evidence
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'document_links' AND column_name = 'evidence_json'
            ) THEN
                ALTER TABLE document_links RENAME COLUMN evidence_json TO evidence;
            END IF;
        END $$;
    """)
    
    # 13. Rename pubmed_meta.authors_jsonb to pubmed_meta.authors
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pubmed_meta' AND column_name = 'authors_jsonb'
            ) THEN
                ALTER TABLE pubmed_meta RENAME COLUMN authors_jsonb TO authors;
            END IF;
        END $$;
    """)
    
    # 14. Rename pubmed_meta.affiliations_jsonb to pubmed_meta.affiliations
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pubmed_meta' AND column_name = 'affiliations_jsonb'
            ) THEN
                ALTER TABLE pubmed_meta RENAME COLUMN affiliations_jsonb TO affiliations;
            END IF;
        END $$;
    """)
    
    # 15. Rename pubmed_meta.esummary_jsonb to pubmed_meta.esummary
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pubmed_meta' AND column_name = 'esummary_jsonb'
            ) THEN
                ALTER TABLE pubmed_meta RENAME COLUMN esummary_jsonb TO esummary;
            END IF;
        END $$;
    """)
    
    # 16. Rename pubmed_meta.efetch_header_jsonb to pubmed_meta.efetch_header
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pubmed_meta' AND column_name = 'efetch_header_jsonb'
            ) THEN
                ALTER TABLE pubmed_meta RENAME COLUMN efetch_header_jsonb TO efetch_header;
            END IF;
        END $$;
    """)
    
    # 17. Rename indication_dictionaries.synonyms_jsonb to indication_dictionaries.synonyms
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'indication_dictionaries' AND column_name = 'synonyms_jsonb'
            ) THEN
                ALTER TABLE indication_dictionaries RENAME COLUMN synonyms_jsonb TO synonyms;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert JSONB field names back to _jsonb suffix."""
    
    # 1. Revert assets.names to assets.names_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'assets' AND column_name = 'names'
            ) THEN
                ALTER TABLE assets RENAME COLUMN names TO names_jsonb;
            END IF;
        END $$;
    """)
    
    # 2. Revert trial_versions.raw_data to trial_versions.raw_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trial_versions' AND column_name = 'raw_data'
            ) THEN
                ALTER TABLE trial_versions RENAME COLUMN raw_data TO raw_jsonb;
            END IF;
        END $$;
    """)
    
    # 3. Revert trial_versions.changes to trial_versions.changes_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trial_versions' AND column_name = 'changes'
            ) THEN
                ALTER TABLE trial_versions RENAME COLUMN changes TO changes_jsonb;
            END IF;
        END $$;
    """)
    
    # 4. Revert trial_versions.meta to trial_versions.metadata_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'trial_versions' AND column_name = 'meta'
            ) THEN
                ALTER TABLE trial_versions RENAME COLUMN meta TO metadata_jsonb;
            END IF;
        END $$;
    """)
    
    # 5. Revert studies.extracted_data to studies.extracted_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'studies' AND column_name = 'extracted_data'
            ) THEN
                ALTER TABLE studies RENAME COLUMN extracted_data TO extracted_jsonb;
            END IF;
        END $$;
    """)
    
    # 6. Revert patents.links to patents.links_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'patents' AND column_name = 'links'
            ) THEN
                ALTER TABLE patents RENAME COLUMN links TO links_jsonb;
            END IF;
        END $$;
    """)
    
    # 7. Revert signals.meta to signals.metadata_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'signals' AND column_name = 'meta'
            ) THEN
                ALTER TABLE signals RENAME COLUMN meta TO metadata_jsonb;
            END IF;
        END $$;
    """)
    
    # 8. Revert signal_evidence.meta to signal_evidence.metadata_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'signal_evidence' AND column_name = 'meta'
            ) THEN
                ALTER TABLE signal_evidence RENAME COLUMN meta TO metadata_jsonb;
            END IF;
        END $$;
    """)
    
    # 9. Revert documents.r_components to documents.r_components_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'documents' AND column_name = 'r_components'
            ) THEN
                ALTER TABLE documents RENAME COLUMN r_components TO r_components_jsonb;
            END IF;
        END $$;
    """)
    
    # 10. Revert documents.s_components to documents.s_components_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'documents' AND column_name = 's_components'
            ) THEN
                ALTER TABLE documents RENAME COLUMN s_components TO s_components_jsonb;
            END IF;
        END $$;
    """)
    
    # 11. Revert document_tables.table_data to document_tables.table_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'document_tables' AND column_name = 'table_data'
            ) THEN
                ALTER TABLE document_tables RENAME COLUMN table_data TO table_jsonb;
            END IF;
        END $$;
    """)
    
    # 12. Revert document_links.evidence to document_links.evidence_json
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'document_links' AND column_name = 'evidence'
            ) THEN
                ALTER TABLE document_links RENAME COLUMN evidence TO evidence_json;
            END IF;
        END $$;
    """)
    
    # 13. Revert pubmed_meta.authors to pubmed_meta.authors_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pubmed_meta' AND column_name = 'authors'
            ) THEN
                ALTER TABLE pubmed_meta RENAME COLUMN authors TO authors_jsonb;
            END IF;
        END $$;
    """)
    
    # 14. Revert pubmed_meta.affiliations to pubmed_meta.affiliations_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pubmed_meta' AND column_name = 'affiliations'
            ) THEN
                ALTER TABLE pubmed_meta RENAME COLUMN affiliations TO affiliations_jsonb;
            END IF;
        END $$;
    """)
    
    # 15. Revert pubmed_meta.esummary to pubmed_meta.esummary_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pubmed_meta' AND column_name = 'esummary'
            ) THEN
                ALTER TABLE pubmed_meta RENAME COLUMN esummary TO esummary_jsonb;
            END IF;
        END $$;
    """)
    
    # 16. Revert pubmed_meta.efetch_header to pubmed_meta.efetch_header_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'pubmed_meta' AND column_name = 'efetch_header'
            ) THEN
                ALTER TABLE pubmed_meta RENAME COLUMN efetch_header TO efetch_header_jsonb;
            END IF;
        END $$;
    """)
    
    # 17. Revert indication_dictionaries.synonyms to indication_dictionaries.synonyms_jsonb
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'indication_dictionaries' AND column_name = 'synonyms'
            ) THEN
                ALTER TABLE indication_dictionaries RENAME COLUMN synonyms TO synonyms_jsonb;
            END IF;
        END $$;
    """)