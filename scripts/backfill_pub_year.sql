-- Quick backfill for pub_year field
-- Extract year from published_at where pub_year is null

UPDATE documents 
SET pub_year = EXTRACT(YEAR FROM published_at)::INTEGER
WHERE pub_year IS NULL 
  AND published_at IS NOT NULL;

-- Set default is_open_access to false where null
UPDATE documents 
SET is_open_access = false
WHERE is_open_access IS NULL;

-- Verify the backfill
SELECT 
    COUNT(*) as total_docs,
    COUNT(pub_year) as docs_with_year,
    COUNT(is_open_access) as docs_with_oa_flag
FROM documents;
