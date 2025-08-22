# scripts/rq.sh
# Requires: $PSQL_DSN is set (and your Python env has ncfd importable)

rq_fill() {
  psql "$PSQL_DSN" -v ON_ERROR_STOP=1 -f db/fill_review_queue.sql
}

rq_next() {
  local row
  row="$(psql "$PSQL_DSN" -Atc "SELECT rq_id||E'\t'||nct_id||E'\t'||COALESCE(sponsor_text,'')
                                 FROM review_queue
                                ORDER BY created_at
                                LIMIT 1")" || return $?
  if [[ -z "$row" ]]; then echo "Queue is empty."; return 1; fi
  IFS=$'\t' read -r RQ_ID NCT SPON <<<"$row"
  echo "Next: rq_id=$RQ_ID  nct=$NCT  sponsor=$SPON"
}

rqc() {
  local id="${1:-$(psql "$PSQL_DSN" -Atc "SELECT rq_id FROM review_queue ORDER BY created_at LIMIT 1")}"
  [[ -z "$id" ]] && { echo "Queue is empty."; return 1; }
  psql "$PSQL_DSN" -c "
    SELECT (c->>'company_id')::int AS cid,
           ROUND((c->>'p')::numeric, 3) AS p,
           c->>'name' AS name
    FROM review_queue, LATERAL jsonb_array_elements(candidates) AS c
    WHERE rq_id = $id
    ORDER BY (c->>'p')::numeric DESC
    LIMIT 12;"
}

rqa() {
  local cid="$1"
  local id="${2:-$(psql "$PSQL_DSN" -Atc "SELECT rq_id FROM review_queue ORDER BY created_at LIMIT 1")}"
  if [[ -z "$cid" || -z "$id" ]]; then echo "Usage: rqa <company_id> [rq_id]"; return 1; fi
  python -m ncfd.mapping.cli review-accept "$id" --company-id "$cid" --apply-trial || { echo "review-accept failed (exit $?)"; return 1; }
  psql "$PSQL_DSN" -q -c "DELETE FROM review_queue WHERE rq_id = $id" >/dev/null
  rq_next
}

rqr() {
  local reason="${*:-'skip'}"
  local id
  id="$(psql "$PSQL_DSN" -Atc "SELECT rq_id FROM review_queue ORDER BY created_at LIMIT 1")"
  [[ -z "$id" ]] && { echo "Queue is empty."; return 1; }
  psql "$PSQL_DSN" -q -c "DELETE FROM review_queue WHERE rq_id = $id" >/dev/null
  echo "Rejected rq_id=$id :: $reason"
  rq_next
}

# Add an ignore pattern (regex). Example:
#   rqi '(?i)[[:<:]]national cancer institute[[:>:]]' "ignore NCI"
rqi() {
  local pattern="$1"; shift
  local note="${*:-manual add}"
  if [[ -z "$pattern" ]]; then echo "Usage: rqi <regex-pattern> [note]"; return 1; fi
  psql "$PSQL_DSN" -v ON_ERROR_STOP=1 -c \
    "INSERT INTO resolver_ignore_sponsor(pattern, note)
     VALUES ($$${pattern}$$, $$${note}$$)
     ON CONFLICT DO NOTHING;"
  echo "Added ignore: $pattern"
}

rqa_top() {
  local minp="${1:-0.90}"  # require at least this probability
  local id cid p
  id="$(psql "$PSQL_DSN" -Atc "SELECT rq_id FROM review_queue ORDER BY created_at LIMIT 1")" || return $?
  [[ -z "$id" ]] && { echo "Queue empty."; return 1; }
  read -r cid p <<<"$(psql "$PSQL_DSN" -Atc "
    SELECT (c->>'company_id')::int, (c->>'p')::numeric
    FROM review_queue, LATERAL jsonb_array_elements(candidates) c
    WHERE rq_id=$id ORDER BY (c->>'p')::numeric DESC LIMIT 1
  ")"
  if [[ -z "$cid" ]]; then echo "No candidates."; return 1; fi
  awk "BEGIN{exit !($p >= $minp)}" || { echo "Top p=$p < min $minp; skipping."; return 1; }
  python -m ncfd.mapping.cli review-accept "$id" --company-id "$cid" --apply-trial || return $?
  psql "$PSQL_DSN" -q -c "DELETE FROM review_queue WHERE rq_id=$id" >/dev/null
  echo "Accepted rq_id=$id cid=$cid p=$p"
}
