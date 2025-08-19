\set ON_ERROR_STOP on

-- Insert Roche (parent) if missing
INSERT INTO companies (name, website_domain)
SELECT 'F. Hoffmann-La Roche Ltd', 'roche.com'
WHERE NOT EXISTS (
  SELECT 1 FROM companies
  WHERE name ILIKE 'F.%Hoffmann%Roche%' OR name ILIKE 'Roche%'
);

-- Insert Genentech (child) if missing
INSERT INTO companies (name, website_domain)
SELECT 'Genentech, Inc.', 'gene.com'
WHERE NOT EXISTS (
  SELECT 1 FROM companies
  WHERE name ILIKE 'Genentech%'
);

-- If companies has parent_company_id, set Genentech -> Roche
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='companies' AND column_name='parent_company_id'
  ) THEN
    UPDATE companies g
    SET parent_company_id = r.company_id
    FROM companies r
    WHERE g.name ILIKE 'Genentech%'
      AND (r.name ILIKE 'F.%Hoffmann%Roche%' OR r.name ILIKE 'Roche%');
  END IF;
END$$;

-- If you have an alias table, add some common aliases (idempotent)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema='public' AND table_name='company_aliases'
  ) THEN
    INSERT INTO company_aliases (company_id, alias)
    SELECT r.company_id, x.a
    FROM companies r
    CROSS JOIN (VALUES
      ('Roche'),
      ('F. Hoffmann-La Roche'),
      ('F Hoffmann La Roche')
    ) AS x(a)
    WHERE r.name ILIKE 'F.%Hoffmann%Roche%' OR r.name ILIKE 'Roche%'
    ON CONFLICT DO NOTHING;

    INSERT INTO company_aliases (company_id, alias)
    SELECT g.company_id, x.a
    FROM companies g
    CROSS JOIN (VALUES
      ('Genentech'),
      ('Genentech Inc')
    ) AS x(a)
    WHERE g.name ILIKE 'Genentech%'
    ON CONFLICT DO NOTHING;
  END IF;
END$$;

-- Show the ids you’ll use later
WITH r AS (
  SELECT company_id FROM companies
  WHERE name ILIKE 'F.%Hoffmann%Roche%' OR name ILIKE 'Roche%'
  ORDER BY company_id LIMIT 1
), g AS (
  SELECT company_id FROM companies
  WHERE name ILIKE 'Genentech%'
  ORDER BY company_id LIMIT 1
)
SELECT
  (SELECT company_id FROM r) AS roche_id,
  (SELECT company_id FROM g) AS genentech_id;
