\set ON_ERROR_STOP on

-- Company ids
WITH r AS (
  SELECT company_id FROM companies
   WHERE name_norm IN (
     lower(regexp_replace('F. Hoffmann-La Roche Ltd','[^a-z0-9]+',' ','g')),
     lower(regexp_replace('Roche','[^a-z0-9]+',' ','g'))
   )
   ORDER BY company_id LIMIT 1
),
g AS (
  SELECT company_id FROM companies
   WHERE name_norm IN (
     lower(regexp_replace('Genentech, Inc.','[^a-z0-9]+',' ','g')),
     lower(regexp_replace('Genentech','[^a-z0-9]+',' ','g'))
   )
   ORDER BY company_id LIMIT 1
),
sec AS (
  SELECT lower(ticker) AS t, (security_id)::text AS sid
    FROM securities
   WHERE lower(ticker) IN ('rhhby','rog','dna')
),
pairs AS (
  SELECT r.company_id, s.sid FROM r CROSS JOIN sec s WHERE s.t IN ('rhhby','rog')
  UNION ALL
  SELECT g.company_id, s.sid FROM g CROSS JOIN sec s WHERE s.t = 'dna'
)
INSERT INTO company_securities (company_id, security_id)
SELECT company_id, sid FROM pairs
ON CONFLICT DO NOTHING;

-- Verify using the adaptive view (handles missing columns on securities)
SELECT company_id, company_name, ticker, security_id
  FROM v_company_tickers
 WHERE company_name ILIKE '%Roche%' OR company_name ILIKE '%Genentech%'
 ORDER BY company_id, ticker;
