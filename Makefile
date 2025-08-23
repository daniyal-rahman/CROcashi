# CROcashi Makefile
# =================
# This Makefile provides commands for development, database management, and deployment

# --- Configuration ---
PY ?= python3.11
VENV = .venv
PIP = $(VENV)/bin/pip
PYTHON = $(VENV)/bin/python

# Docker configuration
COMPOSE = docker compose
DB_SVC = db
DB_CONT = ncfd_db

# Load .env into Make variables + export to subprocesses
ifneq (,$(wildcard .env))
include .env
export $(shell awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{print $$1}' .env)
endif

# Database defaults if .env is missing
POSTGRES_USER     ?= ncfd
POSTGRES_PASSWORD ?= ncfd
POSTGRES_DB       ?= ncfd
POSTGRES_HOST     ?= 127.0.0.1
POSTGRES_HOST_PORT ?= 5433
POSTGRES_DSN      ?= postgresql+psycopg2://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@$(POSTGRES_HOST):$(POSTGRES_HOST_PORT)/$(POSTGRES_DB)
DATABASE_URL      ?= $(POSTGRES_DSN)

# Postgres connection settings (host side)
DB_HOST ?= 127.0.0.1
DB_PORT ?= 5433
DB_NAME ?= ncfd
DB_USER ?= ncfd
DB_PASS ?= ncfd

# Inside-container port
DB_HOST_IN ?= 127.0.0.1
DB_PORT_IN ?= 5432

# Use dockerized Postgres 16 client to avoid version mismatch
PG_IMG ?= postgres:16-alpine
NET    ?= ncfd_default

# Colorless, safe PGPASSWORD wrapper
define PSQL_HOST
PGPASSWORD=$(DB_PASS) psql -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME)
endef

define PSQL_CONT
$(COMPOSE) exec $(DB_SVC) env PGPASSWORD=$(DB_PASS) psql -h $(DB_HOST_IN) -p $(DB_PORT_IN) -U $(DB_USER) -d $(DB_NAME)
endef

# --- Phony Targets ---
.PHONY: help setup fmt lint type test \
        db_up db_down db_nuke db_logs db_wait db_psql db_dump db_restore db_sql db_url \
        db_psql_host db_psql_container db_logs_host db_status db_health db_env \
        db_dump_host db_dump_schema_host db_restore_host \
        db_dump_docker db_dump_schema_docker db_restore_docker \
        db_reset db_client_docker db_verify db_verify_file \
        migrate_up migrate_down_one alembic alembic_init \
        run_id resolve_one resolve_batch resolve_one_persist \
        review_list review_show review_accept review_reject \
        batch_dry batch_persist \
        subs_inspect subs_dry subs_load subs_build subs_link subs_link_load \
        review_fill run_all ingest_ctgov

# --- Help ---
help: ## Show this help message
	@echo "CROcashi Makefile - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  setup              - Set up virtual environment and install dependencies"
	@echo "  fmt                - Format code with ruff and black"
	@echo "  lint               - Check code style with ruff and black"
	@echo "  type               - Run type checking with mypy"
	@echo "  test               - Run tests"
	@echo ""
	@echo "Database Management:"
	@echo "  db_up              - Start database with Docker Compose"
	@echo "  db_down            - Stop database with Docker Compose"
	@echo "  db_nuke            - Stop database and remove volumes"
	@echo "  db_wait            - Wait for database to be healthy"
	@echo "  db_reset           - Full database reset (nuke, up, wait, migrate)"
	@echo "  db_verify          - Verify database health and schema"
	@echo "  db_psql            - Connect to database via Docker Compose"
	@echo "  db_psql_host       - Connect to database from host"
	@echo "  db_psql_container  - Connect to database from inside container"
	@echo "  db_dump            - Dump database to backup file"
	@echo "  db_restore         - Restore database from backup file"
	@echo "  db_sql             - Execute SQL file on database"
	@echo ""
	@echo "Migrations:"
	@echo "  migrate_up         - Run all pending migrations"
	@echo "  migrate_down_one   - Rollback one migration"
	@echo "  alembic            - Run alembic command (use ARGS='history')"
	@echo ""
	@echo "Data Processing:"
	@echo "  resolve_one        - Resolve single sponsor (use SPONSOR='name')"
	@echo "  resolve_batch      - Resolve batch of sponsors"
	@echo "  review_list        - List items in review queue"
	@echo "  review_show        - Show review queue item (use RQ=id)"
	@echo "  review_accept      - Accept review (use RQ=id CID=company_id)"
	@echo "  review_reject      - Reject review (use RQ=id)"
	@echo "  ingest_ctgov       - Ingest ClinicalTrials.gov data"
	@echo "  subs_load          - Load subsidiary data"
	@echo ""
	@echo "Utilities:"
	@echo "  run_id             - Generate run ID for tracking"
	@echo "  run_all            - Full setup: db up, migrate, ingest"

# --- Development Setup ---

setup: ## Set up virtual environment and install dependencies
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e .[dev]
	$(VENV)/bin/pre-commit install
	set -a; source .env; set +a
	@echo "✅ Virtual environment ready. Activate with: source $(VENV)/bin/activate"

fmt: ## Format code with ruff and black
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/black .

lint: ## Check code style with ruff and black
	$(VENV)/bin/ruff check .
	$(VENV)/bin/black --check .

type: ## Run type checking with mypy
	$(VENV)/bin/mypy src

test: ## Run tests
	CONFIG_PROFILE=local $(VENV)/bin/pytest -q

# --- Database Management ---

db_url: ## Show database connection string
	@echo "$(POSTGRES_DSN)"

db_up: ## Start database with Docker Compose
	$(COMPOSE) -f docker-compose.yml up -d $(DB_SVC)

db_down: ## Stop database with Docker Compose
	$(COMPOSE) -f docker-compose.yml down --remove-orphans

db_nuke: ## Stop database and remove volumes
	$(COMPOSE) -f docker-compose.yml down -v

db_logs: ## Show database logs
	$(COMPOSE) -f docker-compose.yml logs -f $(DB_SVC)

db_wait: ## Wait for Postgres to be healthy
	@echo "Waiting for Postgres to be healthy..."
	@for i in $$(seq 1 60); do \
		STATUS=$$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' $(DB_CONT) 2>/dev/null); \
		if [ "$$STATUS" = "healthy" ]; then \
			echo "Postgres healthy ✅"; exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "Postgres failed to become healthy ❌"; docker ps; exit 1

db_psql: ## Connect to database via Docker Compose
	$(COMPOSE) exec $(DB_SVC) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db_psql_host: ## Connect to database from host
	$(PSQL_HOST)

db_psql_container: ## Connect to database from inside container
	$(PSQL_CONT)

db_logs_host: ## Tail database logs
	$(COMPOSE) logs -f $(DB_SVC)

db_status: ## Show running containers and mapped ports
	docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"

db_health: ## Run pg_isready from host
	PGPASSWORD=$(DB_PASS) pg_isready -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME) || true

db_env: ## Show database environment from container inspect
	docker inspect $(DB_CONT) | grep -A0 -B0 '"Env"' -n; true

# Database dump/restore operations
db_dump: ## Dump database to backup file
	@TS=$$(date -u +%Y%m%dT%H%M%SZ); \
	$(COMPOSE) exec -T $(DB_SVC) pg_dump -U $(POSTGRES_USER) -d $(POSTGRES_DB) -Fc > /tmp/ncfd.$${TS}.dump; \
	echo "Wrote /tmp/ncfd.$${TS}.dump"

db_dump_host: ## Dump full database to backup.sql from host
	PGPASSWORD=$(DB_PASS) pg_dump -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME) > backup.sql

db_dump_schema_host: ## Dump schema only to schema.sql from host
	PGPASSWORD=$(DB_PASS) pg_dump -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME) -s > schema.sql

db_dump_docker: ## Full backup using dockerized pg_dump -> backup.sql
	docker run --rm --network $(NET) -e PGPASSWORD=$(DB_PASS) $(PG_IMG) \
	  pg_dump -h $(DB_SVC) -U $(DB_USER) -d $(DB_NAME) > backup.sql

db_dump_schema_docker: ## Schema-only backup using dockerized pg_dump -> schema.sql
	docker run --rm --network $(NET) -e PGPASSWORD=$(DB_PASS) $(PG_IMG) \
	  pg_dump -h $(DB_SVC) -U $(DB_USER) -d $(DB_NAME) -s > schema.sql

# Usage: make db_restore FILE=/path/to/ncfd.dump
db_restore: ## Restore database from dump file (use FILE=path/to/dump)
ifndef FILE
	$(error Provide FILE=/path/to/dump)
endif
	@docker cp $(FILE) $(DB_CONT):/tmp/restore.dump
	@$(COMPOSE) exec -T $(DB_SVC) pg_restore -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c -v /tmp/restore.dump
	@$(COMPOSE) exec -T $(DB_SVC) rm -f /tmp/restore.dump

db_restore_host: ## Restore backup.sql into $(DB_NAME)_restore from host
	PGPASSWORD=$(DB_PASS) createdb -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) $(DB_NAME)_restore
	PGPASSWORD=$(DB_PASS) psql -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME)_restore -f backup.sql

db_restore_docker: ## Restore backup.sql using dockerized psql into $(DB_NAME)_restore
	docker run --rm --network $(NET) -e PGPASSWORD=$(DB_PASS) $(PG_IMG) \
	  createdb -h $(DB_SVC) -U $(DB_USER) $(DB_NAME)_restore || true
	docker run --rm --network $(NET) -e PGPASSWORD=$(DB_PASS) -i $(PG_IMG) \
	  psql -h $(DB_SVC) -U $(DB_USER) -d $(DB_NAME)_restore < backup.sql

# Usage: make db_sql FILE=src/ncfd/db/fill_review_queue.sql
db_sql: ## Execute SQL file on database (use FILE=path/to.sql)
ifndef FILE
	$(error Provide FILE=path/to.sql)
endif
	@cat $(FILE) | $(COMPOSE) exec -T $(DB_SVC) psql -v ON_ERROR_STOP=1 -U $(POSTGRES_USER) -d $(POSTGRES_DB)

# Database verification and reset
db_reset: ## Full database reset: nuke volumes, start Postgres, wait, run migrations
	$(MAKE) db_nuke
	$(MAKE) db_up
	$(MAKE) db_wait
	$(MAKE) migrate_up

db_client_docker: ## Interactive psql (dockerized pg16) to host database
	docker run --rm -it --network host -e PGPASSWORD=$(DB_PASS) $(PG_IMG) \
	  psql -h 127.0.0.1 -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME)

db_verify: ## Run sanity checks to ensure database is healthy and schema is complete
	@echo "== pg_isready =="
	@PGPASSWORD=$(DB_PASS) pg_isready -h $(DB_HOST) -p $(DB_PORT) -U $(DB_USER) -d $(DB_NAME) || true
	@echo "\n== server version / current DB =="
	@$(MAKE) db_psql_host -s -e <<< "SELECT version(); SELECT current_database();"
	@echo "\n== required extensions =="
	@$(MAKE) db_psql_host -s -e <<< "CREATE EXTENSION IF NOT EXISTS pg_trgm; SELECT extname FROM pg_extension ORDER BY 1;"
	@echo "\n== expected tables present =="
	@$(MAKE) db_psql_host -s -e <<< "SELECT count(*) AS table_count FROM information_schema.tables WHERE table_schema='public';"
	@echo "\n== critical tables exist =="
	@$(MAKE) db_psql_host -s -e <<< "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('companies','securities','review_queue','resolver_decisions','trials','trial_versions','ingest_runs') ORDER BY 1;"
	@echo "\n== key indexes/constraints spot-check =="
	@$(MAKE) db_psql_host -s -e <<< "\d review_queue"
	@$(MAKE) db_psql_host -s -e <<< "\d resolver_decisions"
	@echo "\n== basic write/read smoke test (transaction rolled back) =="
	@$(PSQL_HOST) -v ON_ERROR_STOP=1 \
		-c "BEGIN;" \
		-c "INSERT INTO companies(name,name_norm,cik) VALUES ('_smoke_','_smoke_',9999999) ON CONFLICT (cik) DO NOTHING;" \
		-c "SELECT company_id, name FROM companies WHERE cik=9999999;" \
		-c "ROLLBACK;"
	@$(PSQL_HOST) -At -c "SELECT count(*) FROM companies WHERE cik=9999999;" | sed 's/^/smoke_count_should_be_zero=/'

db_verify_file: ## Run database verification using SQL file
	@$(MAKE) db_sql FILE=scripts/db_verify.sql

# --- Migrations ---

alembic_init: ## Initialize Alembic (one-time setup)
	@# one-time (if you haven't created migrations folder)
	$(VENV)/bin/alembic init alembic

migrate_up: ## Run all pending migrations
	POSTGRES_DSN=$(POSTGRES_DSN) DATABASE_URL=$(DATABASE_URL) $(VENV)/bin/alembic upgrade head

migrate_down_one: ## Rollback one migration
	POSTGRES_DSN=$(POSTGRES_DSN) DATABASE_URL=$(DATABASE_URL) $(VENV)/bin/alembic downgrade -1

# Usage: make alembic ARGS="history"
alembic: ## Run alembic command (use ARGS='history' or other commands)
	POSTGRES_DSN=$(POSTGRES_DSN) DATABASE_URL=$(DATABASE_URL) $(VENV)/bin/alembic $(ARGS)

# --- Data Processing ---

# ClinicalTrials.gov ingestion
SINCE ?= 2000-01-01
ingest_ctgov: ## Ingest ClinicalTrials.gov data (use SINCE=YYYY-MM-DD)
	CONFIG_PROFILE=local $(PYTHON) scripts/ingest_ctgov.py --since $(SINCE)

# Resolver CLI commands
run_id: ## Generate run ID for tracking
	$(PYTHON) -c "from datetime import datetime; print(datetime.utcnow().strftime('resolver-%Y%m%dT%H%M%SZ'))"

resolve_one: ## Resolve single sponsor (use SPONSOR='company name')
	PYTHONPATH=src $(PYTHON) -m ncfd.mapping.cli resolve-one "$(SPONSOR)" --cfg config/resolver.yaml --k 25

resolve_batch: ## Resolve batch of sponsors
	PYTHONPATH=src $(PYTHON) -m ncfd.mapping.cli resolve-batch --cfg config/resolver.yaml --limit 25

resolve_one_persist: ## Resolve single sponsor and persist results (use SPONSOR='name' NCT=id RUN_ID=id)
	PYTHONPATH=src $(PYTHON) -m ncfd.mapping.cli resolve-one "$(SPONSOR)" --cfg config/resolver.yaml --k 25 --persist --nct $(NCT) --run-id $(RUN_ID)

# Review queue management
review_list: ## List items in review queue
	@PYTHONPATH=src $(PYTHON) -m ncfd.mapping.cli review-list

review_show: ## Show review queue item (use RQ=id)
	@PYTHONPATH=src $(PYTHON) -m ncfd.mapping.cli review-show $(RQ)

# Usage: make review_accept RQ=123 CID=6968 [APPLY=1]
review_accept: ## Accept review (use RQ=id CID=company_id [APPLY=1])
ifndef RQ
	$(error Provide RQ=<rq_id> and CID=<company_id>)
endif
ifndef CID
	$(error Provide CID=<company_id>)
endif
	@PYTHONPATH=src $(PYTHON) -m ncfd.mapping.cli review-accept $(RQ) --company-id $(CID) $(if $(APPLY),--apply-trial,)

# Usage: make review_reject RQ=123 [LABEL=1]
review_reject: ## Reject review (use RQ=id [LABEL=1])
ifndef RQ
	$(error Provide RQ=<rq_id>)
endif
	@PYTHONPATH=src $(PYTHON) -m ncfd.mapping.cli review-reject $(RQ) $(if $(LABEL),--label,)

# Batch processing
batch_dry: ## Run batch resolution in dry-run mode (use N=number)
	PYTHONPATH=src $(PYTHON) -m ncfd.mapping.cli resolve-batch --limit $(N) --cfg config/resolver.yaml

batch_persist: ## Run batch resolution and persist results (use N=number RUN_ID=id)
	PYTHONPATH=src $(PYTHON) -m ncfd.mapping.cli resolve-batch --limit $(N) --cfg config/resolver.yaml --persist --run-id $(RUN_ID) --apply-trial

# Subsidiaries processing
SINCE ?= 2018-01-01
LIM ?= 200

subs_inspect: ## Inspect subsidiary data
	@PYTHONPATH=src $(PYTHON) -m ncfd.ingest.subsidiaries inspect

subs_dry: ## Dry run subsidiary processing (use SINCE=YYYY-MM-DD LIM=number)
	@PYTHONPATH=src $(PYTHON) -m ncfd.ingest.subsidiaries dry --since $(SINCE) --limit $(LIM)

subs_load: ## Load subsidiary data (use SINCE=YYYY-MM-DD LIM=number)
	@PYTHONPATH=src $(PYTHON) -m ncfd.ingest.subsidiaries load --since $(SINCE) --limit $(LIM)

subs_build: ## Alias for subs_load (kept for compatibility)
	$(MAKE) subs_load

subs_link: ## Link subsidiaries (use LIM=number)
	@PYTHONPATH=src $(PYTHON) -m ncfd.ingest.subs_link dry --limit $(LIM)

subs_link_load: ## Load subsidiary links
	@PYTHONPATH=src $(PYTHON) -m ncfd.ingest.subs_link load

# Review queue population
review_fill: ## Populate review queue from trials (no-decisions)
	@RUN_ID=$$(date -u +review-%Y%m%dT%H%M%SZ); \
	echo "RUN_ID=$$RUN_ID"; \
	cat scripts/review_fill.sql | $(COMPOSE) exec -T $(DB_SVC) \
	psql -v ON_ERROR_STOP=1 -U $(POSTGRES_USER) -d $(POSTGRES_DB) -v RUN_ID="$$RUN_ID"

# --- Meta Commands ---

run_all: ## Full setup: start database, run migrations, ingest data
	$(MAKE) db_up
	$(MAKE) db_wait
	$(MAKE) migrate_up
	$(MAKE) ingest_ctgov

# --- Legacy Aliases (for backward compatibility) ---
.PHONY: db_migrate db.psql db.psql.c db.logs db.status db.dump db.dump.schema db.restore db.health db.env

# Legacy database commands (kept for compatibility)
db_migrate: ## Legacy: Create and run auto-generated migration
	POSTGRES_DSN=$(POSTGRES_DSN) DATABASE_URL=$(DATABASE_URL) $(VENV)/bin/alembic revision --autogenerate -m "auto"
	$(MAKE) migrate_up

# Legacy dot-notation commands (kept for compatibility)
db.psql: db_psql_host
db.psql.c: db_psql_container
db.logs: db_logs_host
db.status: db_status
db.health: db_health
db.env: db_env
db.dump: db_dump_host
db.dump.schema: db_dump_schema_host
db.restore: db_restore_host
