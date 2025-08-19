\set ON_ERROR_STOP on

-- Ensure link table exists
CREATE TABLE IF NOT EXISTS company_securities (
  company_id  BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  security_id TEXT   NOT NULL,
  linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, security_id)
);

-- If the table already existed with a non-TEXT type, normalize it to TEXT.
DO $$
DECLARE
  coltype text;
BEGIN
  SELECT data_type
    INTO coltype
    FROM information_schema.columns
   WHERE table_schema='public'
     AND table_name='company_securities'
     AND column_name='security_id';

  IF coltype IS DISTINCT FROM 'text' THEN
    EXECUTE 'ALTER TABLE company_securities
             ALTER COLUMN security_id TYPE TEXT
             USING security_id::text';
  END IF;
END$$;

CREATE INDEX IF NOT EXISTS company_securities_security_id_idx
  ON company_securities (security_id);

-- View: always compare as TEXT to avoid type mismatches
CREATE OR REPLACE VIEW v_company_tickers AS
SELECT
  c.company_id,
  c.name AS company_name,
  s.ticker,
  s.issuer_name,
  s.exchange,
  s.active,
  (s.security_id)::text AS security_id
FROM company_securities cs
JOIN companies  c ON c.company_id = cs.company_id
JOIN securities s ON (s.security_id)::text = (cs.security_id)::text;

-- Smoke test (may return 0 rows until links are made)
SELECT * FROM v_company_tickers ORDER BY company_id, ticker NULLS LAST LIMIT 5;
