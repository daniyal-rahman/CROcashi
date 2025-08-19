#!/usr/bin/env bash
set -euo pipefail

# ---- Config -------------------------------------------------------------------
PSQL_DSN="${PSQL_DSN:-postgresql://ncfd:ncfd@127.0.0.1:5433/ncfd}"

# Resolve ncfd/src (run this from repo root or anywhere containing ./ncfd/src)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/src" ]; then
  _PPATH="$SCRIPT_DIR/src"
elif [ -d "$PWD/ncfd/src" ]; then
  _PPATH="$PWD/ncfd/src"
else
  echo "Couldn't find ncfd/src. Run this from the repo root (where ./ncfd/src exists)."
  exit 1
fi

ncfdrun() { PYTHONPATH="$_PPATH" python -m ncfd.mapping.cli "$@"; }

# ---- Helpers ------------------------------------------------------------------

# Next queue item, skipping ignored sponsors (NCI/NIH/etc) if you've seeded resolver_ignore_sponsor.
next_id() {
  psql "$PSQL_DSN" -t -A -c "
    SELECT q.rq_id
      FROM resolver_review_queue q
      JOIN trials t USING (nct_id)
 LEFT JOIN resolver_ignore_sponsor ig ON t.sponsor_text ~* ig.pattern
     WHERE ig.pattern IS NULL
  ORDER BY q.created_at ASC, q.rq_id ASC
     LIMIT 1;
  "
}

# Return "run_id nct_id sponsor_text" for an rq_id
meta_of() {
  psql "$PSQL_DSN" -t -A -F ' ' -c "
    SELECT q.run_id, q.nct_id, t.sponsor_text
      FROM resolver_review_queue q
      JOIN trials t USING (nct_id)
     WHERE q.rq_id = $1;
  "
}

# Turn rank (1..N) into a company_id, de-duping by company_id first
cid_by_rank() {
  local run_id="$1" nct_id="$2" rnk="$3"
  psql "$PSQL_DSN" -t -A -c "
    WITH feats AS (
      SELECT company_id, p_calibrated AS p
        FROM resolver_features
       WHERE run_id = '$run_id' AND nct_id = '$nct_id'
    ),
    dedup AS (
      SELECT f.*,
             ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY p DESC NULLS LAST) AS rn
        FROM feats f
    ),
    ranked AS (
      SELECT company_id,
             ROW_NUMBER() OVER (ORDER BY p DESC NULLS LAST) AS rnk
        FROM dedup
       WHERE rn = 1
    )
    SELECT company_id FROM ranked WHERE rnk = $rnk;
  " | tr -d '[:space:]'
}

# Top candidate company_id (after de-duping)
top_cid() {
  local run_id="$1" nct_id="$2"
  psql "$PSQL_DSN" -t -A -c "
    WITH feats AS (
      SELECT company_id, p_calibrated AS p
        FROM resolver_features
       WHERE run_id = '$run_id' AND nct_id = '$nct_id'
    ),
    dedup AS (
      SELECT f.*,
             ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY p DESC NULLS LAST) AS rn
        FROM feats f
    )
    SELECT company_id
      FROM dedup
     WHERE rn = 1
  ORDER BY p DESC NULLS LAST
     LIMIT 1;
  " | tr -d '[:space:]'
}

# Pretty table with names; one row per company
print_rich_table() {
  local run_id="$1" nct_id="$2"
  psql "$PSQL_DSN" -c "
    WITH feats AS (
      SELECT company_id,
             p_calibrated AS p,
             (features_jsonb->>'jw_primary')::float           AS jw,
             (features_jsonb->>'token_set_ratio')::float      AS tsr,
             (features_jsonb->>'acronym_exact')::float        AS acro,
             (features_jsonb->>'domain_root_match')::float    AS domain_hit,
             (features_jsonb->>'ticker_string_hit')::float    AS ticker_hit,
             (features_jsonb->>'strong_token_overlap')::float AS strong_tok
        FROM resolver_features
       WHERE run_id = '$run_id' AND nct_id = '$nct_id'
    ),
    dedup AS (
      SELECT f.*,
             ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY p DESC NULLS LAST) AS rn
        FROM feats f
    )
    SELECT ROW_NUMBER() OVER (ORDER BY d.p DESC NULLS LAST) AS rank,
           d.company_id AS cid,
           COALESCE(c.name, '(unknown)') AS name,
           NULLIF(c.website_domain, '')  AS website,
           TO_CHAR(d.p,  '0.000')  AS p,
           TO_CHAR(d.jw, '0.3F')   AS jw,
           TO_CHAR(d.tsr,'0.3F')   AS tsr,
           d.acro        AS acro_hit,
           d.domain_hit  AS domain_hit,
           d.ticker_hit  AS ticker_hit,
           d.strong_tok  AS strong_tok
      FROM dedup d
 LEFT JOIN companies c USING (company_id)
     WHERE d.rn = 1
  ORDER BY d.p DESC NULLS LAST
     LIMIT 20;
  "
}

# Accept: set trials.sponsor_company_id and remove from queue
accept_item() {
  local rq_id="$1" company_id="$2"
  # Pull nct_id (and run_id if you want to audit later)
  read -r RUN_ID NCT_ID SPONSOR <<<"$(meta_of "$rq_id")"

  # Update trial + remove from queue
  psql "$PSQL_DSN" -v cid="$company_id" -v nct="$NCT_ID" -v rq="$rq_id" -c "
    BEGIN;
      UPDATE trials SET sponsor_company_id = :cid WHERE nct_id = :'nct';
      DELETE FROM resolver_review_queue WHERE rq_id = :rq;
    COMMIT;
  " >/dev/null
}

# Reject: just remove from queue (or store a reject somewhere if you like)
# Function to reject an item
reject_item() {
  rq_id=$1
  echo "Rejecting item $rq_id"
  psql "$PSQL_DSN" -c "DELETE FROM resolver_review_queue WHERE rq_id = $rq_id;"
}

# ---- Main loop ----------------------------------------------------------------
while true; do
  RQ_ID="$(next_id | tr -d '[:space:]')"
  if [ -z "${RQ_ID:-}" ]; then echo "No pending items 🎉"; break; fi

  clear
  # This prints the header: time/sponsor and a skinny table
  ncfdrun review-show "$RQ_ID"

  # richer table with names + features (deduped)
  read -r RUN_ID NCT_ID _ <<<"$(meta_of "$RQ_ID")"
  echo
  print_rich_table "$RUN_ID" "$NCT_ID"
  echo
  echo "[1-9] pick rank  |  [a] accept top  |  [p <CID>] pick by company id  |  [r] reject  |  [s] skip  |  [q] quit"
  read -r cmd arg || { echo; break; }

  case "${cmd:-}" in
    q) break ;;
    s) psql "$PSQL_DSN" -v rq="$RQ_ID" -c "UPDATE resolver_review_queue SET created_at = now() WHERE rq_id = :rq;" >/dev/null ;;
    r) reject_item "$RQ_ID" ;;
    a)
      CID="$(top_cid "$RUN_ID" "$NCT_ID")"
      if [ -z "$CID" ]; then
        echo "No candidates to accept; skipping…"; sleep 0.7
      else
        accept_item "$RQ_ID" "$CID"
      fi
      ;;
    p)
      if [[ -z "${arg:-}" || ! "$arg" =~ ^[0-9]+$ ]]; then
        echo "Usage: p <COMPANY_ID>"; sleep 0.7
      else
        accept_item "$RQ_ID" "$arg"
      fi
      ;;
    *)
      if [[ "$cmd" =~ ^[0-9]+$ ]]; then
        CID="$(cid_by_rank "$RUN_ID" "$NCT_ID" "$cmd")"
        if [ -z "$CID" ]; then echo "No candidate at rank $cmd"; sleep 0.7
        else accept_item "$RQ_ID" "$CID"; fi
      else
        echo "Unknown. Use: digits to pick rank | a | p <CID> | r | s | q"; sleep 0.7
      fi
      ;;
  esac
done
