# CROcashi
Clinical Trial evaluator for downstream bin pred

conda activate CROcashi
# 1) Start/confirm Docker DB (port 5433)
make db_up
make db_wait

# 2) Export .env into your current shell (bash/zsh)
set -a
. ./.env
set +a

# 3) Sanity-check it points to 5433
echo "$DATABASE_URL"    # expect: postgresql+psycopg://ncfd:ncfd@127.0.0.1:/ncfd

# 4) Now Alembic will work
alembic history --indicate-current
alembic heads -v


# New
cd ncfd
set -a; source .env; set +a
source venv/bin/activate

make db_up && make db_wait && make migrate_up

export CTG_SINCE='2000-01-01'
export CTG_UNTIL=''                 # optional
export CTG_PAGE_SIZE='500'          # paging chunk size; not a hard cap
export CTG_LIMIT='0'                # 0 = no cap
export CTG_PERSIST_CURSOR='1'       # write to ctgov_ingest_state

PYTHONPATH=ncfd/src python scripts/ingest_ctgov.py
