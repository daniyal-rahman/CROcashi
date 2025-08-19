\set ON_ERROR_STOP on

-- Insert Roche (idempotent)
INSERT INTO companies (name, name_norm, website_domain)
SELECT
  'F. Hoffmann-La Roche Ltd' AS name,
  lower(regexp_replace('F. Hoffmann-La Roche Ltd','[^a-z0-9]+',' ','g')) AS name_norm,
  'roche.com' AS website_domain
WHERE NOT EXISTS (
  SELECT 1 FROM companies
  WHERE name_norm IN (
    lower(regexp_replace('F. Hoffmann-La Roche Ltd','[^a-z0-9]+',' ','g')),
    lower(regexp_replace('Roche','[^a-z0-9]+',' ','g'))
  )
);

-- Insert Genentech (idempotent)
INSERT INTO companies (name, name_norm, website_domain)
SELECT
  'Genentech, Inc.' AS name,
  lower(regexp_replace('Genentech, Inc.','[^a-z0-9]+',' ','g')) AS name_norm,
  'gene.com' AS website_domain
WHERE NOT EXISTS (
  SELECT 1 FROM companies
  WHERE name_norm IN (
    lower(regexp_replace('Genentech, Inc.','[^a-z0-9]+',' ','g')),
    lower(regexp_replace('Genentech','[^a-z0-9]+',' ','g'))
  )
);

-- Link Genentech -> Roche if parent column exists
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
     WHERE table_schema='public' AND table_name='companies' AND column_name='parent_company_id'
  ) THEN
    UPDATE companies g
       SET parent_company_id = r.company_id
      FROM companies r
     WHERE g.name_norm = lower(regexp_replace('Genentech, Inc.','[^a-z0-9]+',' ','g'))
       AND r.name_norm IN (
             lower(regexp_replace('F. Hoffmann-La Roche Ltd','[^a-z0-9]+',' ','g')),
             lower(regexp_replace('Roche','[^a-z0-9]+',' ','g'))
           )
       AND (g.parent_company_id IS DISTINCT FROM r.company_id);
  END IF;
END$$;

-- Show ids
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
)
SELECT
  (SELECT company_id FROM r) AS roche_id,
  (SELECT company_id FROM g) AS genentech_id;
