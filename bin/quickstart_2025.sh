#!/usr/bin/env bash
set -euo pipefail

# -------- settings you can tweak ----------
CTG_SINCE="${CTG_SINCE:-2025-01-01}"   # only ingest CT.gov from 2025+
DB_PORT="${POSTGRES_PORT:-5433}"        # maps to docker compose db port
DB_HOST="${POSTGRES_HOST:-127.0.0.1}"
DB_USER="${POSTGRES_USER:-ncfd}"
DB_PASS="${POSTGRES_PASSWORD:-ncfd}"
DB_NAME="${POSTGRES_DB:-ncfd}"
SEC_TICKERS_JSON="data/sec/company_tickers_exchange.json"
SUBMISSIONS_DIR="data/sec/submissions"  # optional, only used if you flip ALIASES=former/all
ALIASES="${ALIASES:-former}"            # none | former | all
VENV=".venv"
# -----------------------------------------

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Ensuring tools"
command -v docker >/dev/null || { echo "Docker is required"; exit 1; }
command -v python3 >/dev/null || { echo "Python3 is required"; exit 1; }
command -v curl >/dev/null || { echo "curl is required"; exit 1; }

echo "==> Writing .env (psycopg2 driver, port ${DB_PORT})"
cat > .env <<EOF
CONFIG_PROFILE=local
POSTGRES_USER=${DB_USER}
POSTGRES_PASSWORD=${DB_PASS}
POSTGRES_DB=${DB_NAME}
POSTGRES_PORT=${DB_PORT}
POSTGRES_HOST=${DB_HOST}

# SQLAlchemy / Alembic (force psycopg2)
DATABASE_URL=postgresql+psycopg2://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}
POSTGRES_DSN=postgresql+psycopg2://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}

# DuckDB / S3 (optional; safe defaults)
DUCKDB_PATH=./data/duckdb/analytics.duckdb
S3_ENDPOINT_URL=http://localhost:9000
S3_REGION=us-east-1
S3_BUCKET=ncfd-raw
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_USE_SSL=false

# polite IDs for public APIs (set your email later)
UNPAYWALL_EMAIL=you@example.com
OPENALEX_EMAIL=you@example.com
SEC_USER_AGENT="CROcashi/0.1 (you@example.com)"
NCBI_TOOL=ncfd
NCBI_EMAIL=you@example.com
EOF

echo "==> Starting Postgres in Docker"
docker compose up -d db

echo "==> Waiting for Postgres to be healthy..."
for i in $(seq 1 60); do
  if docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' ncfd_db 2>/dev/null | grep -q healthy; then
    echo "Postgres healthy ✅"
    break
  fi
  sleep 1
  if [[ $i -eq 60 ]]; then
    echo "Postgres failed to become healthy ❌"; docker ps; exit 1
  fi
done

echo "==> Creating Python venv & installing package"
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install -U pip
# dev extras are fine; adjust if you want minimal
"${VENV}/bin/pip" install -e .[dev]

echo "==> Alembic migrations (psycopg2)"
POSTGRES_DSN="postgresql+psycopg2://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}" \
  "${VENV}/bin/alembic" upgrade head

echo "==> Seed exchanges whitelist from config"
PYTHONPATH=ncfd/src "${VENV}/bin/python" - <<'PY'
import yaml, sys
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from ncfd.db.session import get_engine

s = sessionmaker(bind=get_engine())()
data = yaml.safe_load(open("ncfd/config/exchanges.yml"))
for ex in data["exchanges"]:
    s.execute(text("""
        INSERT INTO exchanges(code,mic,name,country,is_allowed,metadata)
        VALUES (:code,:mic,:name,:country,:is_allowed,'{}'::jsonb)
        ON CONFLICT (code) DO UPDATE
          SET mic=:mic,name=:name,country=:country,is_allowed=:is_allowed
    """), ex)
# hard-disable CN/HK if present
s.execute(text("UPDATE exchanges SET is_allowed=FALSE WHERE country IN ('CN','HK')"))
s.commit()
print("Seeded exchanges ✅")
PY

echo "==> Download SEC company tickers JSON"
mkdir -p "$(dirname "${SEC_TICKERS_JSON}")"
curl -sSL -H "User-Agent: CROcashi/0.1 (you@example.com)" \
  -o "${SEC_TICKERS_JSON}" \
  https://www.sec.gov/files/company_tickers_exchange.json

echo "==> Ingest SEC issuers + active listings (enforces whitelist)"
PYTHONPATH=ncfd/src "${VENV}/bin/python" -m ncfd.ingest.sec --json "${SEC_TICKERS_JSON}"

if [[ "${ALIASES}" != "none" ]]; then
  echo "==> (Optional) Download SEC submissions (may take time; can Ctrl-C to skip)"
  mkdir -p "${SUBMISSIONS_DIR}"
  # Pull a focused set first: names overlapping unresolved sponsor_text
  echo "Building focus CIK list..."
  psql -At <<'SQL' > /tmp/ciks_focus.txt
WITH unresolved AS (
  SELECT DISTINCT sponsor_text
  FROM trials
  WHERE sponsor_text IS NOT NULL AND sponsor_text <> ''
    AND sponsor_company_id IS NULL
),
cands AS (
  SELECT DISTINCT c.cik
  FROM companies c
  JOIN unresolved u
    ON c.name ILIKE u.sponsor_text || '%'
    OR c.name ILIKE '%' || u.sponsor_text || '%'
)
SELECT cik FROM cands ORDER BY cik;
SQL

  echo "Fetching submissions for focus CIKs (polite rate)..."
  PYTHONPATH=ncfd/src "${VENV}/bin/python" - <<PY
import os, time, concurrent.futures, urllib.request
ua = "CROcashi/0.1 (you@example.com)"
os.makedirs("${SUBMISSIONS_DIR}", exist_ok=True)
ciks = [l.strip() for l in open("/tmp/ciks_focus.txt") if l.strip().isdigit()]
def fetch(cik):
    cik10 = f"{int(cik):010d}"
    url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
    out = f"${SUBMISSIONS_DIR}/CIK{cik10}.json"
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return "skip", cik10
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=30) as r, open(out, "wb") as w:
            w.write(r.read())
        time.sleep(0.25)
        return "ok", cik10
    except Exception as e:
        if os.path.exists(out): os.remove(out)
        return "fail", f"{cik10} {e}"
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    for status, info in ex.map(fetch, ciks):
        if status != "skip":
            print(status, info)
PY

  if [[ "${ALIASES}" == "former" || "${ALIASES}" == "all" ]]; then
    echo "==> Ingest former names -> company_aliases"
    PYTHONPATH=ncfd/src "${VENV}/bin/python" -m ncfd.ingest.sec_submissions --dir "${SUBMISSIONS_DIR}"
  fi

  # (Optional) for ALIASES=all, you could also feed Exhibit-21 text into ncfd.ingest.aliases later
fi

echo "==> Ingest CT.gov (since ${CTG_SINCE})"
CONFIG_PROFILE=local CTG_SINCE="${CTG_SINCE}" \
  PYTHONPATH=ncfd/src "${VENV}/bin/python" scripts/ingest_ctgov.py --since "${CTG_SINCE}"

echo "==> Deterministic sponsor->company mapping pass"
PYTHONPATH=ncfd/src "${VENV}/bin/python" - <<'PY'
from collections import Counter
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from ncfd.db.session import get_engine
from ncfd.mapping.deterministic import resolve_company
s = sessionmaker(bind=get_engine())()
rows = s.execute(text("""
  SELECT DISTINCT sponsor_text
  FROM trials
  WHERE sponsor_text IS NOT NULL AND sponsor_text <> '' AND sponsor_company_id IS NULL
""")).fetchall()
methods = Counter(); updates = []
for (sponsor,) in rows:
    r = resolve_company(s, sponsor)
    if r:
        updates.append({"cid": r.company_id, "sponsor": sponsor})
        methods[r.method] += 1
if updates:
    s.execute(text("""
      UPDATE trials
         SET sponsor_company_id = :cid
       WHERE sponsor_company_id IS NULL AND sponsor_text = :sponsor
    """), updates)
    s.commit()
print(f"Resolved now: {sum(methods.values())} / {len(rows)}")
print("By method:", dict(methods))
s.close()
PY

echo "==> Smoke checks"
psql <<'SQL'
-- CT.gov rows limited to since-date (should all be 2025+ last_update_posted_date)
SELECT MIN(last_update_posted_date) AS min_update,
       MAX(last_update_posted_date) AS max_update,
       COUNT(*) AS trials
FROM trials;

-- 1:1 latest trial version per trial
SELECT
  (SELECT COUNT(*) FROM trials) AS trials,
  (SELECT COUNT(*) FROM (
     SELECT DISTINCT ON (trial_id) trial_id
     FROM trial_versions
     ORDER BY trial_id, captured_at DESC, trial_version_id DESC
  ) x) AS latest_versions;

-- Exchanges guardrails: only allowed among active listings
SELECT DISTINCT e.code
FROM securities s JOIN exchanges e USING(exchange_id)
WHERE s.status='active' AND e.is_allowed=TRUE
ORDER BY 1;

-- No duplicate active tickers
SELECT ticker_norm, COUNT(*) c
FROM securities
WHERE status='active'
GROUP BY 1 HAVING COUNT(*) > 1;

-- How many trials mapped to a company_id?
SELECT COUNT(*) AS trials_total,
       COUNT(sponsor_company_id) AS trials_mapped
FROM trials;
SQL

echo "==> All done 🎉  (CTG_SINCE=${CTG_SINCE}, ALIASES=${ALIASES})"
