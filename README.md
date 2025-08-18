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
echo "$DATABASE_URL"    # expect: postgresql+psycopg://ncfd:ncfd@127.0.0.1:5433/ncfd

# 4) Now Alembic will work
alembic history --indicate-current
alembic heads -v




set -a; source .env; set +a

