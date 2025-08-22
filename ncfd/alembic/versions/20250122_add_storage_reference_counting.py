"""Add storage reference counting system

This migration adds:
1. storage_objects table for tracking content references
2. storage_references table for tracking what references each object
3. Functions for incrementing/decrementing reference counts
4. Integration with documents and studies tables

Revision ID: 20250122_add_storage_refcounting
Revises: 20250122_fix_pivotal_study_card_trigger
Create Date: 2025-01-22 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250122_add_storage_refcounting'
down_revision = '20250122_fix_pivotal_study_card_trigger'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create storage_objects table for reference counting
    if not _table_exists("storage_objects"):
        op.create_table(
            "storage_objects",
            sa.Column("object_id", sa.BigInteger(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("storage_uri", sa.Text(), nullable=False),
            sa.Column("backend_type", sa.String(20), nullable=False),  # local, s3
            sa.Column("tier", sa.Text(), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("refcount", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.PrimaryKeyConstraint("object_id"),
            sa.CheckConstraint("tier IN ('local','s3')", name="ck_storage_objects_tier"),
            sa.UniqueConstraint("sha256", "backend_type", name="uq_storage_objects_sha256_backend")
        )
        
        # Create indexes for efficient querying
        op.create_index("ix_storage_objects_sha256", "storage_objects", ["sha256"])
        op.create_index("ix_storage_objects_backend_type", "storage_objects", ["backend_type"])
        op.create_index("ix_storage_objects_tier", "storage_objects", ["tier"])
        op.create_index("ix_storage_objects_refcount", "storage_objects", ["refcount"])
        op.create_index("ix_storage_objects_last_accessed", "storage_objects", ["last_accessed"])
        op.create_index("ix_storage_objects_created_at", "storage_objects", ["created_at"])
    
    # Create storage_references table to track what references each object
    if not _table_exists("storage_references"):
        op.create_table(
            "storage_references",
            sa.Column("reference_id", sa.BigInteger(), nullable=False),
            sa.Column("object_id", sa.BigInteger(), nullable=False),
            sa.Column("reference_type", sa.String(50), nullable=False),  # document, study, asset, etc.
            sa.Column("referenced_id", sa.BigInteger(), nullable=False),  # ID of the referencing entity
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("reference_id"),
            sa.ForeignKeyConstraint(["object_id"], ["storage_objects.object_id"], ondelete="CASCADE"),
            sa.UniqueConstraint("object_id", "reference_type", "referenced_id", name="uq_storage_references_unique")
        )
        
        # Create indexes
        op.create_index("ix_storage_references_object_id", "storage_references", ["object_id"])
        op.create_index("ix_storage_references_reference", "storage_references", ["reference_type", "referenced_id"])
    
    # Create function to increment reference count
    op.execute("""
        CREATE OR REPLACE FUNCTION increment_storage_refcount(
            p_sha256 TEXT,
            p_backend_type TEXT,
            p_reference_type TEXT,
            p_reference_id BIGINT
        ) RETURNS INTEGER LANGUAGE plpgsql AS $$
        DECLARE
            v_object_id BIGINT;
            v_refcount INTEGER;
        BEGIN
            -- Get or create storage object
            INSERT INTO storage_objects (sha256, storage_uri, backend_type, tier, size_bytes, refcount, last_accessed)
            VALUES (
                p_sha256,
                p_backend_type || '://' || p_sha256,
                p_backend_type,
                p_backend_type,  -- tier same as backend_type for now
                0,  -- Will be updated when content is stored
                1
            )
            ON CONFLICT (sha256, backend_type) 
            DO UPDATE SET 
                refcount = storage_objects.refcount + 1,
                last_accessed = NOW()
            RETURNING object_id, refcount INTO v_object_id, v_refcount;
            
            -- Add reference record
            INSERT INTO storage_references (object_id, reference_type, referenced_id)
            VALUES (v_object_id, p_reference_type, p_reference_id)
            ON CONFLICT (object_id, reference_type, referenced_id) DO NOTHING;
            
            RETURN v_refcount;
        END $$;
    """)
    
    # Create function to decrement reference count
    op.execute("""
        CREATE OR REPLACE FUNCTION decrement_storage_refcount(
            p_sha256 TEXT,
            p_backend_type TEXT,
            p_reference_type TEXT,
            p_reference_id BIGINT
        ) RETURNS INTEGER LANGUAGE plpgsql AS $$
        DECLARE
            v_object_id BIGINT;
            v_refcount INTEGER;
        BEGIN
            -- Get object ID
            SELECT object_id INTO v_object_id
            FROM storage_objects 
            WHERE sha256 = p_sha256 AND backend_type = p_backend_type;
            
            IF v_object_id IS NULL THEN
                RETURN 0;
            END IF;
            
            -- Remove reference record
            DELETE FROM storage_references 
            WHERE object_id = v_object_id 
              AND reference_type = p_reference_type 
              AND referenced_id = p_reference_id;
            
            -- Decrement refcount
            UPDATE storage_objects 
            SET refcount = GREATEST(0, refcount - 1),
                last_accessed = NOW()
            WHERE object_id = v_object_id
            RETURNING refcount INTO v_refcount;
            
            RETURN COALESCE(v_refcount, 0);
        END $$;
    """)
    
    # Create function to get objects eligible for cleanup
    op.execute("""
        CREATE OR REPLACE FUNCTION get_cleanup_candidates(
            p_max_age_days INTEGER DEFAULT 30,
            p_min_refcount INTEGER DEFAULT 0
        ) RETURNS TABLE(
            object_id BIGINT,
            sha256 TEXT,
            storage_uri TEXT,
            backend_type TEXT,
            content_size BIGINT,
            refcount INTEGER,
            created_at TIMESTAMPTZ,
            last_accessed TIMESTAMPTZ
        ) LANGUAGE plpgsql AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                so.object_id,
                so.sha256,
                so.storage_uri,
                so.backend_type,
                so.content_size,
                so.refcount,
                so.created_at,
                so.last_accessed
            FROM storage_objects so
            WHERE so.refcount <= p_min_refcount
              AND so.last_accessed < NOW() - INTERVAL '1 day' * p_max_age_days
            ORDER BY so.last_accessed ASC;
        END $$;
    """)


def downgrade() -> None:
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS get_cleanup_candidates(INTEGER, INTEGER);")
    op.execute("DROP FUNCTION IF EXISTS decrement_storage_refcount(TEXT, TEXT, TEXT, BIGINT);")
    op.execute("DROP FUNCTION IF EXISTS increment_storage_refcount(TEXT, TEXT, TEXT, BIGINT);")
    
    # Drop tables
    if _table_exists("storage_references"):
        op.drop_index("ix_storage_references_reference", table_name="storage_references")
        op.drop_index("ix_storage_references_object_id", table_name="storage_references")
        op.drop_table("storage_references")
    
    if _table_exists("storage_objects"):
        op.drop_index("ix_storage_objects_created_at", table_name="storage_objects")
        op.drop_index("ix_storage_objects_last_accessed", table_name="storage_objects")
        op.drop_index("ix_storage_objects_refcount", table_name="storage_objects")
        op.drop_index("ix_storage_objects_backend_type", table_name="storage_objects")
        op.drop_index("ix_storage_objects_sha256", table_name="storage_objects")
        op.drop_table("storage_objects")


# Helper functions for idempotent operations
def _table_exists(table_name: str) -> bool:
    """Check if table exists."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    return table_name in inspector.get_table_names()
