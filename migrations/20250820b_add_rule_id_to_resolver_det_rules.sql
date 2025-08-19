BEGIN;

-- Add a surrogate PK column expected by the code
ALTER TABLE resolver_det_rules
  ADD COLUMN IF NOT EXISTS rule_id BIGSERIAL;

-- If there’s no PK yet, make rule_id the PK
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.resolver_det_rules'::regclass
      AND contype = 'p'
  ) THEN
    ALTER TABLE resolver_det_rules
      ADD CONSTRAINT resolver_det_rules_pkey PRIMARY KEY (rule_id);
  END IF;
END$$;

-- Helpful index for the query plan the code uses
CREATE INDEX IF NOT EXISTS ix_resolver_det_rules_priority
  ON resolver_det_rules (priority DESC, rule_id ASC);

COMMIT;
