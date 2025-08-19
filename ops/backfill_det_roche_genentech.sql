-- backfill_det_roche_genentech.sql
WITH m AS (
  SELECT
    t.nct_id,
    rr.company_id,
    rr.priority,
    ROW_NUMBER() OVER (PARTITION BY t.nct_id ORDER BY rr.priority ASC) AS rn
  FROM trials t
  JOIN resolver_det_rules rr
    ON t.sponsor_text ~* rr.pattern
  WHERE (t.sponsor_company_id IS NULL OR t.sponsor_company_id = 0)
),
best AS (
  SELECT nct_id, company_id FROM m WHERE rn = 1
)
UPDATE trials t
SET sponsor_company_id = b.company_id
FROM best b
WHERE t.nct_id = b.nct_id;
