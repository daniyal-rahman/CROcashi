-- migrations/20250818_company_orgs.sql
-- 1) Aliases for name/brand normalization
CREATE TABLE IF NOT EXISTS company_aliases (
  company_id   bigint NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  alias        text   NOT NULL,
  created_at   timestamptz DEFAULT now(),
  PRIMARY KEY (company_id, alias)
);
CREATE INDEX IF NOT EXISTS idx_company_aliases_alias_trgm ON company_aliases USING gin (alias gin_trgm_ops);

-- 2) Parent/child relationships with dating
CREATE TABLE IF NOT EXISTS company_relationships (
  parent_company_id bigint NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  child_company_id  bigint NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  rel_type          text NOT NULL DEFAULT 'subsidiary',
  start_date        date,
  end_date          date,
  created_at        timestamptz DEFAULT now(),
  PRIMARY KEY (parent_company_id, child_company_id, rel_type)
);

-- 3) View to get the ultimate parent (“canonical”) for rollups
CREATE OR REPLACE RECURSIVE VIEW v_company_canonical AS
WITH RECURSIVE up (company_id, canonical_id) AS (
  SELECT c.company_id, c.company_id
  FROM companies c
  WHERE NOT EXISTS (
    SELECT 1 FROM company_relationships r
    WHERE r.child_company_id = c.company_id
      AND r.end_date IS NULL
  )
  UNION
  SELECT r.child_company_id, up.canonical_id
  FROM company_relationships r
  JOIN up ON up.company_id = r.parent_company_id
  WHERE r.end_date IS NULL
)
SELECT company_id, canonical_id
FROM up;
