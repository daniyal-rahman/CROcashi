Look at global prompt for the repo goal.
Here’s what this piece does—and why it matters:

### What we’re making work

1. **Schema + data plumbing**

   * Stood up Postgres/Alembic, seeded an **exchange whitelist**, loaded **SEC tickers** → populated `companies`/`securities`.
2. **Trial → company mapping (resolver)**

   * Deterministic rules (exact/alias/domain) first; else **probabilistic ranking** with calibrated p.
   * Decisions go to `resolver_decisions`; candidate features to `resolver_features`; ambiguous cases → **review\_queue**.
3. **Human-in-the-loop**

   * You reviewed a few and accepted them; the CLI writes back the decision and (optionally) updates `trials.sponsor_company_id`.
4. **Learning loop**

   * Export **(features + human/auto decisions)** → CSV → fit **weights + calibrator** → update `config/resolver.yaml` → re-run.
   * We debugged the export (run\_id mismatch) so training data actually flows.

### Why this is crucial for a precision-first failure detector

* **Join to markets:** Without the right `company_id`/ticker, you can’t track **US-listed** catalysts, price windows, or precision metrics (P\@K, median 5-day move).
* **Signal correctness:** Gates like **S5 (class “graveyard”)**, ownership, and asset lineage depend on knowing the **right sponsor**; wrong mapping = false flags.
* **T-14 freeze & audits:** Freezing features and auditing misses require a clean key between **trial ↔ company**.
* **Keep the queue tiny:** Better calibration/weights → fewer reviews, more deterministic short-circuits → **higher precision** (the core goal).

### “Done” for this slice means

* Trials reliably get a **correct `sponsor_company_id`** (US-listed focus), with:

  * Deterministic short-circuiting for exact/alias/domain hits,
  * A small, reviewable queue for the rest,
  * A working **export → train → config update → re-run** loop.

Once this is solid, we use those clean links to power the **signals/gates** (S1–S9, G1–G4), calibrate **likelihood ratios**, set stop rules, and produce the **few, near-certain failure flags** you care about.


# 0) From repo root (the one that has /src and /data)
#    Activate your venv if you haven't.
. .venv/bin/activate

# 1) Env for DB + SQLAlchemy
export PSQL_DSN='postgresql://ncfd:ncfd@127.0.0.1:5433/ncfd'
export DATABASE_URL='postgresql+psycopg2://ncfd:ncfd@127.0.0.1:5433/ncfd'

# 2) Bring up Postgres and run Alembic migrations
make db_up && make db_wait && make migrate_up

# 3) Quick DB sanity
psql "$PSQL_DSN" -c '\dt+'
psql "$PSQL_DSN" -c "SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns WHERE table_schema='public' ORDER BY 1,2,3;"


# --------------------------- INGEST: EXCHANGES + SEC ---------------------------

# 4) Seed the exchange whitelist
#    NOTE: the CLI expects a YAML path that exists on disk.
#    **BUG PREVIOUSLY**: using 'ncfd/config/exchanges.yml' from repo root  ➜ FileNotFoundError.
#    **FIX**: point to the file under /src
PYTHONPATH=src python -m ncfd.ingest.exchanges src/ncfd/config/exchanges.yml

# 5) Load SEC tickers (companies + active securities)
#    **BUG SEEN**: FileNotFoundError when the CWD wasn't repo root or the path was wrong.
#    **FIX**: verify the file exists first.
ls -l data/sec/company_tickers_exchange.json
PYTHONPATH=src python -m ncfd.ingest.sec --json data/sec/company_tickers_exchange.json --start 1990-01-01

# 6) (Optional) Former names from SEC submissions JSONs
PYTHONPATH=src python -m ncfd.ingest.sec_submissions --dir data/sec/submissions

# 7) Post-ingest counts
psql "$PSQL_DSN" -c "SELECT COUNT(*) companies   FROM companies;
                     SELECT COUNT(*) securities  FROM securities;
                     SELECT COUNT(*) exchanges   FROM exchanges;"


# ------------------------------- RESOLVER PASSES -------------------------------

# 8) First pass, write features/decisions and enqueue ambiguous items
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --persist --limit 50

# 9) Review queue workflow
PYTHONPATH=src python -m ncfd.mapping.cli review-list
PYTHONPATH=src python -m ncfd.mapping.cli review-show 1
# Accept + write back to trials when you know the company_id:
PYTHONPATH=src python -m ncfd.mapping.cli review-accept 1 -c <company_id> --apply-trial

# 10) (Optional) Ignore common non-issuers to shrink the queue
psql "$PSQL_DSN" -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS resolver_ignore_sponsor(
  pattern   text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO resolver_ignore_sponsor(pattern) VALUES
  ('\mNational Cancer Institute\b'),
  ('\mNational Institutes? of Health\b'),
  ('\mNational Institute of Mental Health\b'),
  ('\bNSABP Foundation\b'),
  ('\bETOP IBCSG Partners Foundation\b'),
  ('\bUniversity\b'),
  ('\bHospital\b'),
  ('\bFoundation$')
ON CONFLICT DO NOTHING;
SQL

# 11) Another pass after seeding ignores
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --persist --limit 100

# **Heads-up bugs/quirks in this section**
# - **BUG PREVIOUSLY**: `resolve-one` does not accept `--apply-trial` (that option exists on resolve-nct/resolve-batch).
#   Use:  PYTHONPATH=src python -m ncfd.mapping.cli resolve-nct NCT01234567 --persist --apply-trial
# - `resolver_decisions` does NOT have created_at — don’t SELECT it there (features table does).


# ------------------------------- EXPORT → TRAIN -------------------------------

# 12) Export training data by RELAXED join (nct_id + company_id)
#     **BUG PREVIOUSLY**: (a) relying on run_id match ➜ empty CSV, (b) using `\copy` via -f ➜ parse error.
#     **FIX**: use relaxed join + one-liner \copy below (writes header + rows).
psql "$PSQL_DSN" -v ON_ERROR_STOP=1 -c "\copy (
  WITH latest_features AS (
    SELECT DISTINCT ON (nct_id, company_id)
           nct_id, company_id, features_jsonb,
           COALESCE(p_calibrated, 0.0) AS p_calibrated,
           created_at
    FROM resolver_features
    WHERE jsonb_typeof(features_jsonb) = 'object'
    ORDER BY nct_id, company_id, created_at DESC
  )
  SELECT
    d.nct_id,
    d.company_id,
    (d.mode = 'accept')::int                                 AS y,
    COALESCE((f.features_jsonb->>'jw_primary')::float, 0.0)           AS jw_primary,
    COALESCE((f.features_jsonb->>'token_set_ratio')::float, 0.0)      AS token_set_ratio,
    COALESCE((f.features_jsonb->>'acronym_exact')::int, 0)            AS acronym_exact,
    COALESCE((f.features_jsonb->>'domain_root_match')::int, 0)        AS domain_root_match,
    COALESCE((f.features_jsonb->>'ticker_string_hit')::int, 0)        AS ticker_string_hit,
    COALESCE((f.features_jsonb->>'academic_keyword_penalty')::int, 0) AS academic_keyword_penalty,
    COALESCE((f.features_jsonb->>'strong_token_overlap')::float, 0.0) AS strong_token_overlap,
    f.p_calibrated
  FROM resolver_decisions d
  JOIN latest_features f USING (nct_id, company_id)
) TO STDOUT WITH CSV HEADER" > training.csv

# Sanity
wc -l training.csv
head -n 5 training.csv

# 13) Train model weights + calibrator and write back to config
#     Install deps if needed (you already did most of these):
pip install -q pyyaml numpy pandas scikit-learn
PYTHONPATH=src python scripts/train_weights.py training.csv --out config/resolver.yaml

# 14) Dry-run with new weights (probabilistic only)
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --cfg config/resolver.yaml --limit 100 --skip-det

# 15) If it looks good, persist + update trials with the new config
PYTHONPATH=src python -m ncfd.mapping.cli resolve-batch --cfg config/resolver.yaml --persist --apply-trial --limit 100


# --------------------------------- CHECKS ---------------------------------

# Decisions / features / queue tallies
psql "$PSQL_DSN" -c "SELECT COUNT(*) FROM resolver_decisions;
                     SELECT COUNT(*) FROM resolver_features;
                     SELECT COUNT(*) FROM review_queue;"

# Show kinds of run_ids (useful to see 'review-' vs 'resolver-' vs other)
psql "$PSQL_DSN" -c "SELECT CASE
  WHEN run_id LIKE 'review-%'   THEN 'review'
  WHEN run_id LIKE 'resolver-%' THEN 'resolver'
  ELSE 'other' END AS kind, COUNT(*) AS n
FROM resolver_decisions GROUP BY 1 ORDER BY 2 DESC;"

psql "$PSQL_DSN" -c "SELECT CASE
  WHEN run_id LIKE 'review-%'   THEN 'review'
  WHEN run_id LIKE 'resolver-%' THEN 'resolver'
  ELSE 'other' END AS kind, COUNT(*) AS n
FROM resolver_features GROUP BY 1 ORDER BY 2 DESC;"

# Strict vs relaxed join counts (diagnoses empty exports)
psql "$PSQL_DSN" -c "SELECT COUNT(*) AS matches_strict
FROM resolver_decisions d JOIN resolver_features f USING (run_id, nct_id, company_id);"

psql "$PSQL_DSN" -c "SELECT COUNT(*) AS matches_relaxed
FROM resolver_decisions d JOIN resolver_features f USING (nct_id, company_id);"
