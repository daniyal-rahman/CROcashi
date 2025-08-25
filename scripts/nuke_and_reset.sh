#!/usr/bin/env bash
set -euo pipefail

# ========= SAFETY CHECKS =========
if [[ "${I_UNDERSTAND:-}" != "YES" ]]; then
  echo "Refusing to run. Export I_UNDERSTAND=YES to proceed."
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

[[ -f "alembic.ini" ]] || { echo "No alembic.ini here. Wrong dir?"; exit 1; }
[[ -f "pyproject.toml" ]] || { echo "No pyproject.toml; continue at your own risk."; }

DB_URL_DEFAULT="postgresql+psycopg2://ncfd:ncfd@127.0.0.1:5432/ncfd"
DB_URL="${DB_URL:-$DB_URL_DEFAULT}"

echo ">>> Using DB_URL=$DB_URL"

# ========= STOP/NUKE DOCKER DB (if any) =========
if command -v docker >/dev/null 2>&1; then
  echo ">>> Docker: bringing down compose (if any)"
  docker compose down -v --remove-orphans 2>/dev/null || true

  echo ">>> Docker: removing stray containers named like postgres/ncfd_db"
  docker ps -a --format '{{.ID}} {{.Image}} {{.Names}}' \
    | awk '/postgres|ncfd_db/ {print $1}' \
    | xargs -r docker rm -f

  echo ">>> Docker: pruning volumes & networks"
  docker volume prune -f || true
  docker network prune -f || true
fi

# ========= DROP LOCAL PG DB (optional) =========
# Set DROP_LOCAL_PG=1 to execute. Requires `dropdb/createdb` and a superuser.
if [[ "${DROP_LOCAL_PG:-0}" == "1" ]]; then
  echo ">>> Dropping & recreating local Postgres database (DROP_LOCAL_PG=1)"
  DB_NAME="$(python3 - <<'PY'
import os, re
url=os.environ.get("DB_URL","")
m=re.search(r'/(?P<db>[^/?]+)(?:[?].*)?$', url)
print(m.group("db") if m else "")
PY
)"
  if [[ -n "$DB_NAME" ]]; then
    dropdb    --if-exists "$DB_NAME" || true
    createdb  "$DB_NAME"
  else
    echo "Could not parse DB name from DB_URL=$DB_URL; skipping local drop/create."
  fi
fi

# ========= DELETE ALEMBIC STATE & PY CACHES =========
echo ">>> Deleting Alembic versions & caches"
rm -rf alembic/versions/* \
       alembic/__pycache__ \
       alembic/versions/__pycache__ || true

echo ">>> Deleting Python caches"
find . -type d -name '__pycache__' -prune -exec rm -rf {} + || true
find . -type f -name '*.py[co]' -delete || true

# ========= MINIMAL ENV.PY (NO MODEL IMPORTS) =========
echo ">>> Replacing alembic/env.py with minimal metadata-free version"
cat > alembic/env.py <<'PY'
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Do NOT import your models here. Keep target_metadata None for stamp/upgrade.
target_metadata = None

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
PY

# ========= FIX alembic.ini DSN =========
echo ">>> Ensuring sqlalchemy.url in alembic.ini"
if ! grep -q '^sqlalchemy.url' alembic.ini; then
  echo "sqlalchemy.url = $DB_URL" >> alembic.ini
else
  sed -i '' "s|^sqlalchemy.url *=.*$|sqlalchemy.url = $DB_URL|g" alembic.ini
fi

# ========= CREATE MINIMAL VENV & REQUIREMENTS (if missing) =========
if [[ ! -d ".venv" ]]; then
  echo ">>> Creating minimal virtualenv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip wheel setuptools
pip install -q "SQLAlchemy>=2.0" "alembic>=1.13" "psycopg2-binary>=2.9"

# ========= STAMP BASE =========
echo ">>> alembic stamp base"
alembic stamp base

# ========= OPTIONAL: QUICK PATCH FOR THE 'text()' COLLISION =========
# Your error: TypeError: 'MappedColumn' object is not callable at postgresql_where=text(...)
# We change it to sa.text(...) defensively across models.
if [[ -f "src/ncfd/db/models.py" ]]; then
  echo ">>> Patching postgresql_where=text(...) -> postgresql_where=sa.text(...), safe if present"
  sed -i '' 's/postgresql_where=text(/postgresql_where=sa.text(/g' src/ncfd/db/models.py || true
  # Ensure `import sqlalchemy as sa` exists
  if ! grep -q '^import sqlalchemy as sa' src/ncfd/db/models.py; then
    sed -i '' '1s/^/import sqlalchemy as sa\n/' src/ncfd/db/models.py
  fi
fi

# ========= REGENERATE CLEAN INITIAL MIGRATION =========
echo ">>> Creating fresh initial migration (no autogenerate metadata yet)"
# Temporarily import metadata only when explicitly requested at autogenerate time
# We’ll append a tiny block to env.py now.
awk '1; /target_metadata = None/ {print "\n# Lazy-load metadata when ALEMBIC_LOAD_METADATA=1\ntry:\n    import os\n    if os.environ.get(\"ALEMBIC_LOAD_METADATA\") == \"1\":\n        from src.ncfd.db.models import Base\n        target_metadata = Base.metadata\nexcept Exception:\n    pass\n"}' alembic/env.py > alembic/env.py.tmp && mv alembic/env.py.tmp alembic/env.py

echo ">>> alembic revision --autogenerate -m 'initial schema'"
ALEMBIC_LOAD_METADATA=1 alembic revision --autogenerate -m "initial schema"

echo ">>> alembic upgrade head"
alembic upgrade head

echo ">>> DONE. Fresh, single-head migration applied."
