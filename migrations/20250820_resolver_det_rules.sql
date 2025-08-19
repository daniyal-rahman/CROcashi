\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS resolver_det_rules (
  pattern      TEXT PRIMARY KEY,
  company_id   BIGINT NOT NULL REFERENCES companies(company_id) ON DELETE CASCADE,
  priority     INT    NOT NULL DEFAULT 100,
  method       TEXT   NOT NULL DEFAULT 'regex',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
DECLARE
  roche_id BIGINT;
  gen_id   BIGINT;
BEGIN
  SELECT company_id
    INTO roche_id
    FROM companies
   WHERE name_norm IN (
          lower(regexp_replace('F. Hoffmann-La Roche Ltd','[^a-z0-9]+',' ','g')),
          lower(regexp_replace('Roche','[^a-z0-9]+',' ','g'))
        )
   ORDER BY company_id
   LIMIT 1;

  SELECT company_id
    INTO gen_id
    FROM companies
   WHERE name_norm IN (
          lower(regexp_replace('Genentech, Inc.','[^a-z0-9]+',' ','g')),
          lower(regexp_replace('Genentech','[^a-z0-9]+',' ','g'))
        )
   ORDER BY company_id
   LIMIT 1;

  IF roche_id IS NULL THEN
    RAISE EXCEPTION 'Roche company_id not found in companies';
  END IF;
  IF gen_id IS NULL THEN
    RAISE EXCEPTION 'Genentech company_id not found in companies';
  END IF;

  -- Roche patterns (broad last, higher priority = smaller number)
  INSERT INTO resolver_det_rules (pattern, company_id, priority, method)
  VALUES ('(?i)\bF\.?\s*Hoffmann[-\s]?La[-\s]?Roche\b', roche_id, 10, 'regex')
  ON CONFLICT (pattern) DO UPDATE SET company_id=EXCLUDED.company_id, priority=EXCLUDED.priority;

  INSERT INTO resolver_det_rules (pattern, company_id, priority, method)
  VALUES ('(?i)\bHoffmann[-\s]?La[-\s]?Roche\b', roche_id, 15, 'regex')
  ON CONFLICT (pattern) DO UPDATE SET company_id=EXCLUDED.company_id, priority=EXCLUDED.priority;

  INSERT INTO resolver_det_rules (pattern, company_id, priority, method)
  VALUES ('(?i)\bRoche\b', roche_id, 30, 'regex')
  ON CONFLICT (pattern) DO UPDATE SET company_id=EXCLUDED.company_id, priority=EXCLUDED.priority;

  -- Genentech patterns
  INSERT INTO resolver_det_rules (pattern, company_id, priority, method)
  VALUES ('(?i)\bGenentech\b', gen_id, 10, 'regex')
  ON CONFLICT (pattern) DO UPDATE SET company_id=EXCLUDED.company_id, priority=EXCLUDED.priority;

  INSERT INTO resolver_det_rules (pattern, company_id, priority, method)
  VALUES ('(?i)\bGenentech,\s*Inc\.?\b', gen_id, 10, 'regex')
  ON CONFLICT (pattern) DO UPDATE SET company_id=EXCLUDED.company_id, priority=EXCLUDED.priority;
END$$;

-- quick check
SELECT COUNT(*) AS n_rules FROM resolver_det_rules;
