"""Add storage objects and references tables

This migration adds the storage_objects table for tracking content references
and the storage_references table for tracking what references each object.
This was previously applied manually via SQL script.

Revision ID: 20250123_add_storage_objects_and_references
Revises: 20250123_add_p_value_column
Create Date: 2025-01-23 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250123_add_storage_objects_and_references'
down_revision = '20250123_add_p_value_column'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create storage_objects table for reference counting (only if it doesn't exist)
    op.execute("""
        CREATE TABLE IF NOT EXISTS storage_objects (
            object_id BIGSERIAL PRIMARY KEY,
            sha256 VARCHAR(64) NOT NULL,
            storage_uri TEXT NOT NULL,
            backend_type VARCHAR(20) NOT NULL,
            tier TEXT NOT NULL CHECK (tier IN ('local','s3')),
            size_bytes BIGINT NOT NULL DEFAULT 0,
            refcount INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_accessed TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata JSONB,
            UNIQUE(sha256, backend_type)
        );
    """)
    
    # Create storage_references table to track what references each object (only if it doesn't exist)
    op.execute("""
        CREATE TABLE IF NOT EXISTS storage_references (
            reference_id BIGSERIAL PRIMARY KEY,
            object_id BIGINT NOT NULL REFERENCES storage_objects(object_id) ON DELETE CASCADE,
            reference_type VARCHAR(50) NOT NULL,
            referenced_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(object_id, reference_type, referenced_id)
        );
    """)
    
    # Create indexes for efficient querying (only if they don't exist)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_storage_objects_sha256 ON storage_objects(sha256);
        CREATE INDEX IF NOT EXISTS ix_storage_objects_backend_type ON storage_objects(backend_type);
        CREATE INDEX IF NOT EXISTS ix_storage_objects_tier ON storage_objects(tier);
        CREATE INDEX IF NOT EXISTS ix_storage_objects_refcount ON storage_objects(refcount);
        CREATE INDEX IF NOT EXISTS ix_storage_objects_last_accessed ON storage_objects(last_accessed);
        CREATE INDEX IF NOT EXISTS ix_storage_objects_created_at ON storage_objects(created_at);
        
        CREATE INDEX IF NOT EXISTS ix_storage_references_object_id ON storage_references(object_id);
        CREATE INDEX IF NOT EXISTS ix_storage_references_reference ON storage_references(reference_type, referenced_id);
    """)
    
    # Add object_id column to documents table if it doesn't exist
    op.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS object_id BIGINT REFERENCES storage_objects(object_id)")

    # Add object_id column to studies table if it doesn't exist
    op.execute("ALTER TABLE studies ADD COLUMN IF NOT EXISTS object_id BIGINT REFERENCES storage_objects(object_id)")

    # Create function to increment reference count (replace if exists)
    op.execute("""
        CREATE OR REPLACE FUNCTION increment_storage_refcount(
            p_sha256 TEXT, p_backend_type TEXT, 
            p_reference_type TEXT, p_reference_id BIGINT
        ) RETURNS INTEGER AS $$
        DECLARE
            v_object_id BIGINT;
            v_new_refcount INTEGER;
        BEGIN
            -- Find or create storage object
            SELECT object_id INTO v_object_id
            FROM storage_objects 
            WHERE sha256 = p_sha256 AND backend_type = p_backend_type;
            
            IF v_object_id IS NULL THEN
                -- Create new storage object
                INSERT INTO storage_objects (sha256, storage_uri, backend_type, tier, size_bytes, refcount, last_accessed)
                VALUES (p_sha256, 
                        CASE p_backend_type 
                            WHEN 'local' THEN 'local://' || p_sha256 || '/content'
                            WHEN 's3' THEN 's3://bucket/docs/' || p_sha256 || '/content'
                            ELSE 'unknown://' || p_sha256 || '/content'
                        END,
                        p_backend_type, 
                        p_backend_type,  -- tier same as backend_type for now
                        0,  -- size_bytes will be updated later
                        1,  -- initial refcount
                        NOW())
                RETURNING object_id INTO v_object_id;
            ELSE
                -- Increment existing refcount
                UPDATE storage_objects 
                SET refcount = refcount + 1,
                    last_accessed = NOW()
                WHERE object_id = v_object_id;
            END IF;
            
            -- Add reference record
            INSERT INTO storage_references (object_id, reference_type, referenced_id)
            VALUES (v_object_id, p_reference_type, p_reference_id)
            ON CONFLICT (object_id, reference_type, referenced_id) DO NOTHING;
            
            -- Return new refcount
            SELECT refcount INTO v_new_refcount
            FROM storage_objects 
            WHERE object_id = v_object_id;
            
            RETURN v_new_refcount;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create function to decrement reference count (replace if exists)
    op.execute("""
        CREATE OR REPLACE FUNCTION decrement_storage_refcount(
            p_sha256 TEXT, p_backend_type TEXT,
            p_reference_type TEXT, p_reference_id BIGINT
        ) RETURNS INTEGER AS $$
        DECLARE
            v_object_id BIGINT;
            v_new_refcount INTEGER;
        BEGIN
            -- Find storage object
            SELECT object_id INTO v_object_id
            FROM storage_objects 
            WHERE sha256 = p_sha256 AND backend_type = p_backend_type;
            
            IF v_object_id IS NULL THEN
                RETURN 0;  -- Nothing to decrement
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
            WHERE object_id = v_object_id;
            
            -- Return new refcount
            SELECT refcount INTO v_new_refcount
            FROM storage_objects 
            WHERE object_id = v_object_id;
            
            RETURN v_new_refcount;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS decrement_storage_refcount(TEXT, TEXT, TEXT, BIGINT)")
    op.execute("DROP FUNCTION IF EXISTS increment_storage_refcount(TEXT, TEXT, TEXT, BIGINT)")
    
    # Drop object_id columns
    op.execute("ALTER TABLE studies DROP COLUMN IF EXISTS object_id")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS object_id")
    
    # Drop indexes
    op.drop_index('ix_storage_references_reference', table_name='storage_references')
    op.drop_index('ix_storage_references_object_id', table_name='storage_references')
    op.drop_index('ix_storage_objects_created_at', table_name='storage_objects')
    op.drop_index('ix_storage_objects_last_accessed', table_name='storage_objects')
    op.drop_index('ix_storage_objects_refcount', table_name='storage_objects')
    op.drop_index('ix_storage_objects_tier', table_name='storage_objects')
    op.drop_index('ix_storage_objects_backend_type', table_name='storage_objects')
    op.drop_index('ix_storage_objects_sha256', table_name='storage_objects')
    
    # Drop tables
    op.drop_table('storage_references')
    op.drop_table('storage_objects')
