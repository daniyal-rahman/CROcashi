-- ============================
-- NCFD SCHEMA AUDIT (read-only)
-- ============================

\echo '=== 0) Context ==='
SELECT current_database() AS db, current_schema() AS schema, version();

-- ----------------------------------------
-- 1) ENUMS present and their value sets
-- ----------------------------------------
\echo '=== 1) ENUMS (user-defined types & labels) ==='
SELECT n.nspname AS schema, t.typname AS enum_name,
       string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder) AS labels
FROM pg_type t
JOIN pg_enum e ON e.enumtypid = t.oid
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname = 'public'
GROUP BY 1,2
ORDER BY 1,2;

-- Expected enums to exist with controlled values:
--  exchanges, catalysts.certainty, disclosures.source_type, gates.g_id,
--  signals.s_id, signals.severity, studies.doc_type, studies.oa_status,
--  studies.coverage_level, patent_assignments.type, lr_tables.scope,
--  runs.status, run_artifacts.artifact_type, trials.phase, trials.status

-- ---------------------------------------------------
-- 2) Column TYPE / NULL / DEFAULT sanity spot-checks
-- ---------------------------------------------------
\echo '=== 2) Column type / nullability / defaults (spot checks) ==='
WITH checklist AS (
  SELECT * FROM (VALUES
    ('trials','nct_id','text', 'NO', NULL),
    ('trials','is_pivotal',NULL, 'NO', 'false'),
    ('securities','ticker','text','NO',NULL),
    ('securities','exchange',NULL,'NO',NULL),
    ('securities','active',NULL,'NO','true'),
    ('securities','is_adr',NULL,'NO','false'),
    ('scores','run_id','text','NO',NULL),
    ('signals','s_id',NULL,'NO',NULL),
    ('signals','severity',NULL,'NO',NULL),
    ('gates','g_id',NULL,'NO',NULL),
    ('gates','fired_bool',NULL,'NO','false'),
    ('studies','doc_type',NULL,'NO',NULL),
    ('studies','oa_status',NULL,'NO',NULL),
    ('studies','coverage_level',NULL,'NO',NULL)
  ) AS t(table_name, column_name, expected_data_type, expected_is_nullable, expected_default)
)
SELECT c.table_name, c.column_name,
       c.data_type, c.udt_name,
       c.is_nullable, c.column_default,
       chk.expected_data_type, chk.expected_is_nullable, chk.expected_default,
       CASE
         WHEN chk.expected_data_type IS NOT NULL AND c.data_type <> chk.expected_data_type THEN 'TYPE_MISMATCH'
         WHEN chk.expected_is_nullable IS NOT NULL AND c.is_nullable <> chk.expected_is_nullable THEN 'NULLABILITY_MISMATCH'
         WHEN chk.expected_default IS NOT NULL
              AND coalesce(c.column_default,'') NOT ILIKE '%'||chk.expected_default||'%' THEN 'DEFAULT_MISSING'
         ELSE 'OK'
       END AS status
FROM information_schema.columns c
JOIN checklist chk ON chk.table_name=c.table_name AND chk.column_name=c.column_name
WHERE c.table_schema='public'
ORDER BY 1,2;

-- Note: If companies.cik should be TEXT (not BIGINT), check here:
\echo '--- companies.cik type ---'
SELECT data_type, udt_name FROM information_schema.columns
WHERE table_schema='public' AND table_name='companies' AND column_name='cik';

-- === 3) Unique constraints expected (PASS if found) ===
WITH expected_uniques AS (
  SELECT * FROM (VALUES
    ('trials',        ARRAY['nct_id']::text[], NULL::text),
    ('securities',    ARRAY['ticker'],         NULL),
    ('companies',     ARRAY['cik'],            'WHERE (cik IS NOT NULL)'),
    ('trial_versions',ARRAY['trial_id','sha256'], NULL),
    ('studies',       ARRAY['hash'],           'WHERE (hash IS NOT NULL)'),
    ('signals',       ARRAY['trial_id','s_id'], NULL),
    ('gates',         ARRAY['trial_id','g_id'],  NULL),
    ('scores',        ARRAY['trial_id','run_id'], NULL),
    ('lr_tables',     ARRAY['scope','id_code','universe_tag','effective_from'], NULL),
    ('patents',       ARRAY['jurisdiction','number'], NULL),
    ('markets',       ARRAY['ticker','date'], NULL)   -- change to (security_id,date) if you normalize later
  ) AS t(table_name, cols, predicate)
),
actual_uniques AS (
  SELECT
    i.relname                           AS index_name,
    c.relname                           AS table_name,
    idx.indisunique                     AS is_unique,
    array_agg(a.attname ORDER BY k.ord) AS cols_name,          -- name[]
    pg_get_expr(idx.indpred, idx.indrelid) AS predicate
  FROM pg_index idx
  JOIN pg_class c        ON c.oid = idx.indrelid
  JOIN pg_namespace ns   ON ns.oid = c.relnamespace AND ns.nspname='public'
  JOIN pg_class i        ON i.oid = idx.indexrelid
  JOIN unnest(idx.indkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
  JOIN pg_attribute a     ON a.attrelid = c.oid AND a.attnum = k.attnum
  WHERE idx.indisunique
  GROUP BY 1,2,3,5
),
actual_uniques_cast AS (
  SELECT
    table_name,
    is_unique,
    -- cast name[] -> text[] explicitly
    ARRAY(SELECT x::text FROM unnest(cols_name) AS x) AS cols_text,
    predicate
  FROM actual_uniques
)
SELECT
  eu.table_name,
  eu.cols              AS expected_cols,
  eu.predicate         AS expected_predicate,
  COALESCE((
    SELECT 'PASS'
    FROM actual_uniques_cast au
    WHERE au.table_name = eu.table_name
      AND au.is_unique
      AND au.cols_text = eu.cols
      AND COALESCE(
            regexp_replace(au.predicate,'\s+',' ','g'),
            ''
          )
          =
          COALESCE(
            regexp_replace(eu.predicate,'\s+',' ','g'),
            ''
          )
    LIMIT 1
  ), 'MISSING') AS status
FROM expected_uniques eu
ORDER BY 1;



-- --------------------------------------------
-- 4) Quick duplicate scans for the uniques
-- --------------------------------------------
\echo '=== 4) Duplicate scans (rows >1 indicate trouble) ==='
-- trials.nct_id
SELECT 'trials.nct_id' AS check, nct_id, COUNT(*) AS cnt
FROM trials GROUP BY 1,2 HAVING COUNT(*)>1;
-- securities.ticker
SELECT 'securities.ticker' AS check, ticker, COUNT(*) AS cnt
FROM securities GROUP BY 1,2 HAVING COUNT(*)>1;
-- companies.cik (ignoring NULL)
SELECT 'companies.cik' AS check, cik, COUNT(*) AS cnt
FROM companies WHERE cik IS NOT NULL GROUP BY 1,2 HAVING COUNT(*)>1;
-- trial_versions (trial_id, sha256)
SELECT 'trial_versions(trial_id,sha256)' AS check, trial_id, sha256, COUNT(*) AS cnt
FROM trial_versions GROUP BY 1,2,3 HAVING COUNT(*)>1;
-- studies.hash (non-null)
SELECT 'studies.hash' AS check, hash, COUNT(*) AS cnt
FROM studies WHERE hash IS NOT NULL GROUP BY 1,2 HAVING COUNT(*)>1;
-- signals (trial_id, s_id)
SELECT 'signals(trial_id,s_id)' AS check, trial_id, s_id, COUNT(*) AS cnt
FROM signals GROUP BY 1,2,3 HAVING COUNT(*)>1;
-- gates (trial_id, g_id)
SELECT 'gates(trial_id,g_id)' AS check, trial_id, g_id, COUNT(*) AS cnt
FROM gates GROUP BY 1,2,3 HAVING COUNT(*)>1;
-- scores (trial_id, run_id)
SELECT 'scores(trial_id,run_id)' AS check, trial_id, run_id, COUNT(*) AS cnt
FROM scores GROUP BY 1,2,3 HAVING COUNT(*)>1;
-- lr_tables composite
SELECT 'lr_tables(scope,id_code,universe_tag,effective_from)' AS check, scope,id_code,universe_tag,effective_from, COUNT(*) AS cnt
FROM lr_tables GROUP BY 1,2,3,4,5 HAVING COUNT(*)>1;
-- patents (jurisdiction, number)
SELECT 'patents(jurisdiction,number)' AS check, jurisdiction, number, COUNT(*) AS cnt
FROM patents GROUP BY 1,2,3 HAVING COUNT(*)>1;
-- markets (ticker, date)
SELECT 'markets(ticker,date)' AS check, ticker, date, COUNT(*) AS cnt
FROM markets GROUP BY 1,2,3 HAVING COUNT(*)>1;

-- --------------------------------------------
-- 5) Expected FOREIGN KEYS presence
-- --------------------------------------------
\echo '=== 5) Foreign keys expected (PASS if found) ==='
WITH expected_fk AS (
  SELECT * FROM (VALUES
    ('securities','company_id','companies','company_id'),
    ('trials','sponsor_company_id','companies','company_id'),
    ('trial_versions','trial_id','trials','trial_id'),
    ('studies','trial_id','trials','trial_id'),
    ('studies','asset_id','assets','asset_id'),
    ('disclosures','trial_id','trials','trial_id'),
    ('signals','trial_id','trials','trial_id'),
    ('signal_evidence','signal_id','signals','signal_id'),
    ('signal_evidence','source_study_id','studies','study_id'),
    ('gates','trial_id','trials','trial_id'),
    ('scores','trial_id','trials','trial_id'),
    ('catalysts','trial_id','trials','trial_id'),
    ('labels','trial_id','trials','trial_id'),
    ('asset_ownership','asset_id','assets','asset_id'),
    ('asset_ownership','company_id','companies','company_id'),
    ('patents','asset_id','assets','asset_id'),
    ('patent_assignments','patent_id','patents','patent_id'),
    ('run_artifacts','run_id','runs','run_id')
  ) AS t(src_table, src_col, dst_table, dst_col)
),
actual_fk AS (
  SELECT
    c.conname,
    src.relname AS src_table,
    a.attname  AS src_col,
    dst.relname AS dst_table,
    d.attname  AS dst_col
  FROM pg_constraint c
  JOIN pg_class src ON src.oid = c.conrelid
  JOIN pg_class dst ON dst.oid = c.confrelid
  JOIN pg_namespace sn ON sn.oid = src.relnamespace AND sn.nspname='public'
  JOIN pg_namespace dn ON dn.oid = dst.relnamespace AND dn.nspname='public'
  JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
  JOIN pg_attribute a ON a.attrelid = src.oid AND a.attnum = k.attnum
  JOIN unnest(c.confkey) WITH ORDINALITY AS fk(attnum, ord) ON fk.ord = k.ord
  JOIN pg_attribute d ON d.attrelid = dst.oid AND d.attnum = fk.attnum
  WHERE c.contype = 'f'
)
SELECT e.src_table, e.src_col, e.dst_table, e.dst_col,
       CASE WHEN EXISTS (
         SELECT 1 FROM actual_fk af
         WHERE af.src_table=e.src_table AND af.src_col=e.src_col
           AND af.dst_table=e.dst_table AND af.dst_col=e.dst_col
       ) THEN 'PASS' ELSE 'MISSING' END AS status
FROM expected_fk e
ORDER BY 1,2;

-- ---------------------------------------------------
-- 6) FKs without supporting indexes (performance)
-- ---------------------------------------------------
\echo '=== 6) FKs missing an index on referencing column(s) ==='
WITH fk_cols AS (
  SELECT
    sn.nspname AS src_schema, src.relname AS src_table,
    array_agg(a.attname ORDER BY k.ord) AS src_cols
  FROM pg_constraint c
  JOIN pg_class src ON src.oid = c.conrelid
  JOIN pg_namespace sn ON sn.oid = src.relnamespace
  JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
  JOIN pg_attribute a ON a.attrelid = src.oid AND a.attnum = k.attnum
  WHERE c.contype = 'f' AND sn.nspname='public'
  GROUP BY 1,2
),
idx_cols AS (
  SELECT
    ns.nspname AS schema, c.relname AS table_name,
    array_agg(a.attname ORDER BY array_position(i.indkey, a.attnum)) FILTER (WHERE i.indisvalid AND NOT i.indisprimary) AS index_cols_sets
  FROM pg_index i
  JOIN pg_class c ON c.oid = i.indrelid
  JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname='public'
  JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum = ANY(i.indkey)
  GROUP BY 1,2
)
SELECT f.src_table, f.src_cols
FROM fk_cols f
LEFT JOIN idx_cols i ON i.schema='public' AND i.table_name=f.src_table
WHERE NOT EXISTS (
  SELECT 1
  FROM unnest(coalesce(i.index_cols_sets, ARRAY[]::text[])) AS idx_cols
  WHERE idx_cols @> f.src_cols    -- index covers all fk cols
)
ORDER BY 1;

-- --------------------------------------------
-- 7) JSONB / trigram index presence (ad-hoc)
-- --------------------------------------------
\echo '=== 7) Helpful indexes present (PASS if found) ==='
WITH want AS (
  SELECT * FROM (VALUES
    ('companies','name_norm','trgm'),
    ('company_aliases','alias','trgm'),
    ('studies','extracted_jsonb','gin'),
    ('trial_versions','raw_jsonb','gin'),
    ('trial_versions','changes_jsonb','gin'),
    ('assets','names_jsonb','gin')
  ) AS t(table_name, col, kind)
),
have AS (
  SELECT
    c.relname AS table_name,
    i.relname AS index_name,
    CASE
      WHEN am.amname='gin' THEN 'gin'
      WHEN am.amname='btree' THEN 'btree'
      ELSE am.amname
    END AS kind,
    pg_get_indexdef(ix.indexrelid) AS indexdef
  FROM pg_index ix
  JOIN pg_class i ON i.oid = ix.indexrelid
  JOIN pg_class c ON c.oid = ix.indrelid
  JOIN pg_am am ON am.oid = i.relam
  JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname='public'
)
SELECT w.table_name, w.col, w.kind,
       CASE
         WHEN EXISTS (
           SELECT 1 FROM have h
           WHERE h.table_name=w.table_name
             AND h.kind = w.kind
             AND h.indexdef ILIKE '%'||w.col||'%'
         ) THEN 'PASS' ELSE 'MISSING'
       END AS status
FROM want w
ORDER BY 1,2;

-- --------------------------------------------
-- 8) Array column typing (should not be generic)
-- --------------------------------------------
\echo '=== 8) ARRAY columns and their element types ==='
SELECT table_name, column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_schema='public' AND data_type='ARRAY'
ORDER BY 1,2;

-- --------------------------------------------
-- 9) Hash/sha columns consistency
-- --------------------------------------------
\echo '=== 9) Hash/sha columns for length & naming consistency ==='
SELECT table_name, column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_schema='public'
  AND (column_name ILIKE '%hash%' OR column_name ILIKE '%sha%')
ORDER BY 1,2;

\echo '--- DONE ---'
