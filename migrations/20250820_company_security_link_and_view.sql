\set ON_ERROR_STOP on

-- 1) Link table (robust to reruns)
CREATE TABLE IF NOT EXISTS company_securities (
  company_id  BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  security_id TEXT   NOT NULL,
  linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, security_id)
);

DO $$
DECLARE coltype text;
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

-- 2) View that adapts to your `securities` columns
DO $$
DECLARE
  has_issuer   boolean;
  has_exchange boolean;
  has_active   boolean;
  sql text;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='securities' AND column_name='issuer_name'
  ) INTO has_issuer;

  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='securities' AND column_name='exchange'
  ) INTO has_exchange;

  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='securities' AND column_name='active'
  ) INTO has_active;

  sql := 'CREATE OR REPLACE VIEW v_company_tickers AS
          SELECT
            c.company_id,
            c.name AS company_name,
            (s.ticker)::text AS ticker, ' ||
         CASE WHEN has_issuer   THEN ' (s.issuer_name)::text AS issuer_name,'
                                   ELSE ' NULL::text AS issuer_name,' END ||
         CASE WHEN has_exchange THEN ' (s.exchange)::text    AS exchange,'
                                   ELSE ' NULL::text AS exchange,' END ||
         CASE WHEN has_active   THEN ' (s.active)::text      AS active,'
                                   ELSE ' NULL::text AS active,' END ||
         ' (s.security_id)::text AS security_id
            FROM company_securities cs
            JOIN companies  c ON c.company_id = cs.company_id
            JOIN securities s ON (s.security_id)::text = (cs.security_id)::text';

  EXECUTE sql;
END$$;

-- 3) Smoke test (ok if empty)
SELECT company_id, company_name, ticker, issuer_name, exchange, active, security_id
FROM v_company_tickers
ORDER BY company_id, ticker NULLS LAST
LIMIT 5;
