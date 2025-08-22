-- Migration: Add storage objects and references tables
-- This migration adds the storage_objects table for tracking content references
-- and the storage_references table for tracking what references each object

-- Create storage_objects table for reference counting
CREATE TABLE IF NOT EXISTS storage_objects (
    object_id BIGSERIAL PRIMARY KEY,
    sha256 VARCHAR(64) NOT NULL,
    storage_uri TEXT NOT NULL,
    backend_type VARCHAR(20) NOT NULL,  -- local, s3
    tier TEXT NOT NULL CHECK (tier IN ('local','s3')),
    size_bytes BIGINT NOT NULL DEFAULT 0,
    refcount INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_accessed TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB,
    UNIQUE(sha256, backend_type)
);

-- Create storage_references table to track what references each object
CREATE TABLE IF NOT EXISTS storage_references (
    reference_id BIGSERIAL PRIMARY KEY,
    object_id BIGINT NOT NULL REFERENCES storage_objects(object_id) ON DELETE CASCADE,
    reference_type VARCHAR(50) NOT NULL,  -- document, study, asset, etc.
    reference_id BIGINT NOT NULL,  -- ID of the referencing entity
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(object_id, reference_type, reference_id)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS ix_storage_objects_sha256 ON storage_objects(sha256);
CREATE INDEX IF NOT EXISTS ix_storage_objects_backend_type ON storage_objects(backend_type);
CREATE INDEX IF NOT EXISTS ix_storage_objects_tier ON storage_objects(tier);
CREATE INDEX IF NOT EXISTS ix_storage_objects_refcount ON storage_objects(refcount);
CREATE INDEX IF NOT EXISTS ix_storage_objects_last_accessed ON storage_objects(last_accessed);
CREATE INDEX IF NOT EXISTS ix_storage_objects_created_at ON storage_objects(created_at);

CREATE INDEX IF NOT EXISTS ix_storage_references_object_id ON storage_references(object_id);
CREATE INDEX IF NOT EXISTS ix_storage_references_reference ON storage_references(reference_type, reference_id);

-- Add object_id column to documents table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS object_id BIGINT REFERENCES storage_objects(object_id);

-- Add object_id column to studies table  
ALTER TABLE studies ADD COLUMN IF NOT EXISTS object_id BIGINT REFERENCES storage_objects(object_id);

-- Create function to increment reference count
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
    INSERT INTO storage_references (object_id, reference_type, reference_id)
    VALUES (v_object_id, p_reference_type, p_reference_id)
    ON CONFLICT (object_id, reference_type, reference_id) DO NOTHING;
    
    -- Return new refcount
    SELECT refcount INTO v_new_refcount
    FROM storage_objects 
    WHERE object_id = v_object_id;
    
    RETURN v_new_refcount;
END;
$$ LANGUAGE plpgsql;

-- Create function to decrement reference count
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
        RETURN 0;
    END IF;
    
    -- Remove reference record
    DELETE FROM storage_references 
    WHERE object_id = v_object_id 
      AND reference_type = p_reference_type 
      AND reference_id = p_reference_id;
    
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

-- Create function to get cleanup candidates (safe to delete)
CREATE OR REPLACE FUNCTION get_cleanup_candidates(
    p_min_age_days INTEGER DEFAULT 30,
    p_max_refcount INTEGER DEFAULT 0
) RETURNS TABLE(
    object_id BIGINT,
    sha256 TEXT,
    storage_uri TEXT,
    backend_type TEXT,
    tier TEXT,
    size_bytes BIGINT,
    refcount INTEGER,
    created_at TIMESTAMPTZ,
    last_accessed TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT so.object_id, so.sha256, so.storage_uri, so.backend_type, 
           so.tier, so.size_bytes, so.refcount, so.created_at, so.last_accessed
    FROM storage_objects so
    WHERE so.refcount <= p_max_refcount
      AND so.created_at < NOW() - INTERVAL '1 day' * p_min_age_days
      AND so.last_accessed < NOW() - INTERVAL '1 day' * p_min_age_days
    ORDER BY so.last_accessed ASC;
END;
$$ LANGUAGE plpgsql;
