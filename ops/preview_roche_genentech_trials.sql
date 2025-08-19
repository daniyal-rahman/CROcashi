\set ON_ERROR_STOP on

WITH ids AS (
  SELECT
    (SELECT company_id FROM companies
      WHERE name_norm IN (
        lower(regexp_replace('F. Hoffmann-La Roche Ltd','[^a-z0-9]+',' ','g')),
        lower(regexp_replace('Roche','[^a-z0-9]+',' ','g'))
      )
      ORDER BY company_id LIMIT 1) AS roche_id,
    (SELECT company_id FROM companies
      WHERE name_norm IN (
        lower(regexp_replace('Genentech, Inc.','[^a-z0-9]+',' ','g')),
        lower(regexp_replace('Genentech','[^a-z0-9]+',' ','g'))
      )
      ORDER BY company_id LIMIT 1) AS gen_id
)
SELECT
  t.nct_id,
  t.sponsor_text,
  CASE
    WHEN t.sponsor_text ~* '(?i)\bGenentech\b' THEN (SELECT gen_id   FROM ids)
    WHEN t.sponsor_text ~* '(?i)\bF\.?\s*Hoffmann[-\s]?La[-\s]?Roche\b' THEN (SELECT roche_id FROM ids)
    WHEN t.sponsor_text ~* '(?i)\bHoffmann[-\s]?La[-\s]?Roche\b' THEN (SELECT roche_id FROM ids)
    WHEN t.sponsor_text ~* '(?i)\bRoche\b' THEN (SELECT roche_id FROM ids)
    ELSE NULL
  END AS det_company_id
FROM trials t
WHERE t.sponsor_text ~* '(genentech|hoffmann[\s-]?la[\s-]?roche|roche\b)'
ORDER BY t.nct_id
LIMIT 200;
