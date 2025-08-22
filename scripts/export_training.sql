\copy (
  WITH best AS (
    SELECT DISTINCT ON (nct_id)
           nct_id,
           company_id AS true_cid,
           sponsor_text_norm,
           decided_at
    FROM resolver_decisions
    WHERE match_type LIKE 'deterministic:%'
       OR match_type = 'probabilistic:accept'
    ORDER BY nct_id, decided_at DESC
  ),
  latest AS (
    SELECT DISTINCT ON (nct_id)
           nct_id, run_id
    FROM resolver_features
    ORDER BY nct_id, run_id DESC
  ),
  cands AS (
    SELECT f.nct_id,
           f.company_id,
           f.features_jsonb,
           COALESCE(f.p_calibrated, f.score_precal) AS p
    FROM resolver_features f
    JOIN latest l USING (nct_id, run_id)
  ),
  pos AS (
    SELECT c.nct_id,
           b.sponsor_text_norm,
           c.company_id,
           1 AS label,
           c.features_jsonb,
           c.p
    FROM cands c
    JOIN best b USING (nct_id)
    WHERE c.company_id = b.true_cid
  ),
  neg AS (
    SELECT c.nct_id,
           b.sponsor_text_norm,
           c.company_id,
           0 AS label,
           c.features_jsonb,
           c.p,
           ROW_NUMBER() OVER (PARTITION BY c.nct_id ORDER BY c.p DESC) AS rk
    FROM cands c
    JOIN best b USING (nct_id)
    WHERE c.company_id <> b.true_cid
  )
  SELECT nct_id, sponsor_text_norm, company_id, label, p, features_jsonb
  FROM pos
  UNION ALL
  SELECT nct_id, sponsor_text_norm, company_id, label, p, features_jsonb
  FROM neg
  WHERE rk <= 20
) TO STDOUT WITH CSV HEADER
