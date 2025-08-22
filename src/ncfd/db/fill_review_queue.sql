WITH latest AS (
  SELECT nct_id, max(run_id) AS run_id
  FROM resolver_features
  GROUP BY nct_id
),
cand AS (
  SELECT f.run_id, f.nct_id, f.company_id,
         COALESCE(f.p_calibrated, f.score_precal) AS p
  FROM resolver_features f
  JOIN latest l
    ON l.nct_id = f.nct_id AND l.run_id = f.run_id
)
INSERT INTO review_queue (run_id, nct_id, sponsor_text, candidates, reason)
SELECT c.run_id,
       c.nct_id,
       t.sponsor_text,
       jsonb_agg(
         jsonb_build_object(
           'company_id', c.company_id,
           'p',          c.p,
           'name',       COALESCE(comp.name, '')
         )
         ORDER BY c.p DESC
       ),
       'prob_review'
FROM cand c
LEFT JOIN resolver_decisions d ON d.nct_id = c.nct_id
LEFT JOIN review_queue rq      ON rq.nct_id = c.nct_id
LEFT JOIN companies comp       ON comp.company_id = c.company_id
LEFT JOIN trials t             ON t.nct_id = c.nct_id
WHERE d.nct_id IS NULL          -- not already decided
  AND rq.rq_id IS NULL          -- not already queued
  AND NOT EXISTS (              -- honor ignore list
      SELECT 1
      FROM resolver_ignore_sponsor ig
      WHERE t.sponsor_text ~* ig.pattern
  )
GROUP BY c.run_id, c.nct_id, t.sponsor_text;
