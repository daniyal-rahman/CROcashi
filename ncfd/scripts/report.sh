# ncfd/scripts/report.py
from __future__ import annotations
import os, datetime as dt
import sqlalchemy as sa

URL = os.environ.get("DATABASE_URL")
engine = sa.create_engine(URL, pool_pre_ping=True)

SQL = """
WITH latest AS (
  SELECT DISTINCT ON (nct_id) nct_id, run_id, decided_at, decided_by, match_type, p_match
  FROM resolver_decisions
  ORDER BY nct_id, decided_at DESC
),
split AS (
  SELECT
    COUNT(*) FILTER (WHERE match_type LIKE 'deterministic:%') AS det,
    COUNT(*) FILTER (WHERE match_type = 'probabilistic:accept') AS prob_accept,
    COUNT(*) FILTER (WHERE match_type = 'probabilistic:review') AS review,
    COUNT(*) FILTER (WHERE match_type = 'probabilistic:reject') AS reject
  FROM latest
),
cov AS (
  SELECT
    COUNT(*) AS total_trials,
    COUNT(*) FILTER (WHERE match_type LIKE 'deterministic:%' OR match_type = 'probabilistic:accept') AS auto_accept
  FROM latest
)
SELECT det, prob_accept, review, reject, total_trials, auto_accept
FROM split, cov;
"""

if __name__ == "__main__":
  with engine.begin() as cx:
    row = cx.execute(sa.text(SQL)).mappings().first()
  if not row:
    print("No decisions yet.")
  else:
    det, prob_acc, review, reject = row["det"], row["prob_accept"], row["review"], row["reject"]
    total, auto = row["total_trials"], row["auto_accept"]
    cov = (auto / total * 100.0) if total else 0.0
    ts = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    print(f"[{ts}] totals={total} auto_accept={auto} ({cov:.1f}%) det={det} prob_accept={prob_acc} review={review} reject={reject}")
