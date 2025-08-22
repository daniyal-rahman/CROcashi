#!/usr/bin/env bash
set -Eeuo pipefail

# --- Env
if [[ ! -f "ncfd/.env" ]]; then
  echo "Missing ncfd/.env"; exit 1
fi
set -a; source ncfd/.env; set +a

# --- Python 3.11 guard
pyver=$(python -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
case "$pyver" in
  3.11.*) : ;;
  *) echo "Need Python 3.11.x; found $pyver"; exit 2 ;;
esac

# --- DB up + migrations
if [[ -f "ncfd/docker-compose.yml" ]]; then
  docker compose -f ncfd/docker-compose.yml up -d --wait
fi
alembic -c ncfd/alembic.ini upgrade head

# --- Sanity checks
psql "$PSQL_DSN" -v ON_ERROR_STOP=1 -q -c "SELECT 1;" >/dev/null
psql "$PSQL_DSN" -q <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='companies') THEN
    RAISE EXCEPTION 'missing table: companies';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='company_aliases') THEN
    RAISE EXCEPTION 'missing table: company_aliases';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='trials') THEN
    RAISE EXCEPTION 'missing table: trials';
  END IF;
END$$;
SQL

# --- Step 1: Subsidiary aliases (deterministic expansion)
python -m ncfd.ingest.subsidiaries load --since 2018-01-01 --limit 2000

# --- Step 2: Batch resolve -> features/decisions
RUN_ID=$(date -u +resolver-%Y%m%dT%H%M%SZ)
export RUN_ID
python -m ncfd.mapping.cli resolve-batch --limit 1000 --persist --run-id "$RUN_ID"

# --- Step 3: Fill review queue
psql "$PSQL_DSN" -v ON_ERROR_STOP=1 -f ncfd/src/ncfd/db/fill_review_queue.sql

# Optional: auto-accept top candidate for N items to bootstrap labels
AUTO_ACCEPT_COUNT=${AUTO_ACCEPT_COUNT:-0}
if (( AUTO_ACCEPT_COUNT > 0 )); then
  # accept top candidate for earliest items (no threshold here; use sparingly)
  for _ in $(seq 1 "$AUTO_ACCEPT_COUNT"); do
    RQ_ID=$(psql "$PSQL_DSN" -Atc "SELECT rq_id FROM review_queue ORDER BY created_at LIMIT 1")
    [[ -z "$RQ_ID" ]] && break
    CID=$(psql "$PSQL_DSN" -Atc \
      "SELECT (c->>'company_id')::int FROM review_queue, LATERAL jsonb_array_elements(candidates) c
       WHERE rq_id=$RQ_ID ORDER BY (c->>'p')::numeric DESC LIMIT 1")
    python -m ncfd.mapping.cli review-accept "$RQ_ID" --company-id "$CID" --apply-trial || true
    psql "$PSQL_DSN" -q -c "DELETE FROM review_queue WHERE rq_id=$RQ_ID" >/dev/null
  done
fi

# --- Step 4: Export -> train -> update thresholds
psql "$PSQL_DSN" -q -v ON_ERROR_STOP=1 -f ncfd/scripts/export_training.sql > training.csv
python ncfd/scripts/train_weights.py

# --- Step 5: Re-run resolve with new config
RUN_ID=$(date -u +resolver-%Y%m%dT%H%M%SZ)
python -m ncfd.mapping.cli resolve-batch --limit 1000 --persist --run-id "$RUN_ID"

# --- Step 6: Report
python -m ncfd.scripts.report || {
  echo "[warn] report module missing; run the SQL below manually."
}
