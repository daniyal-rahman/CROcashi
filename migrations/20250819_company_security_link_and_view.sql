\set ON_ERROR_STOP on

-- Ensure link table exists with TEXT FK
CREATE TABLE IF NOT EXISTS company_securities (
  company_id  BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  security_id TEXT   NOT NULL,
  linked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (company_id, security_id)
);

-- Normalize column type to TEXT if it isn't already
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

-- Build the view based on columns that actually exist in `securities`
DO $$
DECLARE
  has_issuer   boolean;
  has_exchange boolean;
  has_active   boolean;
  stmt text;
BEGIN
  SELECT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='securities' AND column_name='issuer_name')
    INTO has_issuer;

  SELECT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='securities' AND column_name='exchange')
    INTO has_exchange;

  SELECT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='securities' AND column_name='active')
    INTO has_active;

  stmt := 'CREATE OR REPLACE VIEW v_company_tickers AS
           SELECT
             c.company_id,
             c.name AS company_name,
             (s.ticker)::text AS ticker,' ||
          CASE WHEN has_issuer   THEN ' (s.issuer_name)::text AS issuer_name,'   ELSE ' NULL::text AS issuer_name,'   END ||
          CASE WHEN has_exchange THEN ' (s.exchange)::text    AS exchange,'      ELSE ' NULL::text AS e_
