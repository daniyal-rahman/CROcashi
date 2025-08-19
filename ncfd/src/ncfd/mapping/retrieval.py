# ncfd/mapping/retrieval.py
from sqlalchemy import text

RETRIEVAL_SQL = text("""
WITH q AS (SELECT :qnorm::text AS qnorm),
hits AS (
  SELECT
      c.company_id,
      c.name,
      GREATEST(
        similarity(c.name, q.qnorm),
        COALESCE(MAX(similarity(a.alias, q.qnorm)), 0)
      ) AS sim_name,
      COALESCE(MAX((a.alias ILIKE q.qnorm || '%')::int), 0) AS alias_prefix_hit
  FROM companies c
  CROSS JOIN q
  LEFT JOIN company_aliases a ON a.company_id = c.company_id
  WHERE c.name % q.qnorm
     OR a.alias % q.qnorm
     OR c.name ILIKE '%' || q.qnorm || '%'
     OR a.alias ILIKE '%' || q.qnorm || '%'
  GROUP BY c.company_id, c.name
),
ranked AS (
  SELECT
    company_id,
    name,
    sim_name,
    alias_prefix_hit,
    ROW_NUMBER() OVER (
      ORDER BY alias_prefix_hit DESC, sim_name DESC, company_id
    ) AS rnk
  FROM hits
)
SELECT company_id, name
FROM ranked
WHERE rnk <= :k;
""")

def candidate_retrieval(session, qnorm: str, k: int = 50):
    return session.execute(RETRIEVAL_SQL, {"qnorm": qnorm, "k": k}).mappings().all()
