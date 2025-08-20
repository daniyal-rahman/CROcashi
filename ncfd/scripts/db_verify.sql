SELECT version();
SELECT current_database();

-- must-have extension
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SELECT extname FROM pg_extension ORDER BY 1;

-- table count & presence
SELECT count(*) AS table_count
FROM information_schema.tables
WHERE table_schema='public';

SELECT table_name
FROM information_schema.tables
WHERE table_schema='public'
  AND table_name IN ('companies','securities','review_queue','resolver_decisions','trials','trial_versions','ingest_runs')
ORDER BY 1;

-- non-destructive smoke write
BEGIN;
INSERT INTO companies(name, name_norm, cik)
VALUES ('_smoke_', '_smoke_', 9999999)
ON CONFLICT (cik) DO NOTHING;

SELECT company_id, name FROM companies WHERE cik=9999999;
ROLLBACK;
