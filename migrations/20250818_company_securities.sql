-- migrations/20250818_company_securities.sql
CREATE TABLE IF NOT EXISTS company_securities (
  company_id  bigint NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  security_id bigint NOT NULL,  -- PK of public.securities
  PRIMARY KEY (company_id, security_id)
);

CREATE OR REPLACE VIEW v_company_tickers AS
SELECT
  cs.company_id,
  c.name AS company_name,
  s.ticker,
  s.*
FROM company_securities cs
JOIN companies  c ON c.company_id = cs.company_id
JOIN securities s ON s.id = cs.security_id;
