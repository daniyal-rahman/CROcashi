"""add_evidence_spans_table

Revision ID: 1c08e7dd3afe
Revises: 31931857b616
Create Date: 2025-09-24 22:38:54.823520

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1c08e7dd3afe'
down_revision: Union[str, Sequence[str], None] = '31931857b616'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if table already exists using raw SQL
    connection = op.get_bind()
    
    # Check if table exists
    result = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'evidence_spans'
        );
    """)).scalar()
    
    if not result:
        # Create evidence_spans table using raw SQL to avoid Alembic conflicts
        connection.execute(sa.text("""
            CREATE TABLE evidence_spans (
                span_id SERIAL PRIMARY KEY,
                doc_id INTEGER NOT NULL,
                trial_id INTEGER,
                field_name VARCHAR(100) NOT NULL,
                field_value TEXT,
                quote_text TEXT NOT NULL,
                start_char INTEGER,
                end_char INTEGER,
                page_number INTEGER,
                confidence NUMERIC(3, 2),
                extraction_method VARCHAR(50) DEFAULT 'llm' NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                CONSTRAINT fk_evidence_spans_doc_id_documents 
                    FOREIGN KEY(doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE,
                CONSTRAINT fk_evidence_spans_trial_id_trials 
                    FOREIGN KEY(trial_id) REFERENCES trials (trial_id) ON DELETE CASCADE
            );
        """))
        
        # Create indexes
        connection.execute(sa.text("CREATE INDEX idx_evidence_spans_doc_id ON evidence_spans (doc_id);"))
        connection.execute(sa.text("CREATE INDEX idx_evidence_spans_trial_id ON evidence_spans (trial_id);"))
        connection.execute(sa.text("CREATE INDEX idx_evidence_spans_field_name ON evidence_spans (field_name);"))
        connection.execute(sa.text("CREATE INDEX idx_evidence_spans_extraction_method ON evidence_spans (extraction_method);"))
        
        # Create check constraint for confidence range
        connection.execute(sa.text("""
            ALTER TABLE evidence_spans 
            ADD CONSTRAINT ck_evidence_spans_confidence_range 
            CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
        """))
        
        print("Created evidence_spans table successfully")
    else:
        print("evidence_spans table already exists, skipping creation")


def downgrade() -> None:
    """Downgrade schema."""
    # Check if table exists before dropping using raw SQL
    connection = op.get_bind()
    
    # Check if table exists
    result = connection.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'evidence_spans'
        );
    """)).scalar()
    
    if result:
        # Drop check constraint
        connection.execute(sa.text("ALTER TABLE evidence_spans DROP CONSTRAINT IF EXISTS ck_evidence_spans_confidence_range;"))
        
        # Drop indexes
        connection.execute(sa.text("DROP INDEX IF EXISTS idx_evidence_spans_extraction_method;"))
        connection.execute(sa.text("DROP INDEX IF EXISTS idx_evidence_spans_field_name;"))
        connection.execute(sa.text("DROP INDEX IF EXISTS idx_evidence_spans_trial_id;"))
        connection.execute(sa.text("DROP INDEX IF EXISTS idx_evidence_spans_doc_id;"))
        
        # Drop table
        connection.execute(sa.text("DROP TABLE evidence_spans;"))
        
        print("Dropped evidence_spans table successfully")
    else:
        print("evidence_spans table does not exist, skipping drop")
