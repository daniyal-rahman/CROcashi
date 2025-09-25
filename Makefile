# CROcashi Makefile
# =================
# This Makefile provides commands for development, database management, and deployment

# --- Configuration ---
PY ?= python3.12
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
DB_PORT           ?= 5433
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
        review_fill run_all \
        ingest_sec_tickers ingest_sec_filings ingest_sec_backfill ingest_sec_status ingest_sec_all

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
	@echo "  test-cassava       - Run consolidated Cassava pipeline test"
	@echo "  test-cassava-clean - Run Cassava test with fresh database"
	@echo "  test-content-retrieval - Run content retrieval fallback chain test"
	@echo "  test-enhanced-content-retrieval - Run enhanced content retrieval test"
	@echo "  test-pmc-fix - Run PMC content retrieval fix test"
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
	@echo "  resolve_batch_auto - Resolve batch using auto-decider cascade (recommended)"
	@echo "  resolve_batch_auto_test - Quick test batch (25 trials)"
	@echo "  resolve_batch_auto_prod - Production batch (500 trials)"
	@echo "  resolve_batch_auto_custom - Custom batch size (use N=number)"
	@echo "  review_list        - List items in review queue"
	@echo "  review_show        - Show review queue item (use RQ=id)"
	@echo "  review_accept      - Accept review (use RQ=id CID=company_id)"
	@echo "  review_reject      - Reject review (use RQ=id)"

	@echo "  ingest_sec_tickers - Ingest SEC company tickers and securities"
	@echo "  ingest_sec_filings - Run SEC filings pipeline for daily monitoring"
	@echo "  ingest_sec_backfill - Run SEC filings backfill"
	@echo "  ingest_sec_status  - Check SEC pipeline status"
	@echo "  ingest_sec_all     - Run all SEC ingestion tasks"
	@echo "  subs_load          - Load subsidiary data"
	@echo ""
	@echo "Historical Universe Backtest:"
	@echo "  universe_backtest  - Run complete historical universe backtest"
	@echo "  universe_example   - Run example backtest for Alzheimer's trials"
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

test-cassava: ## Run consolidated Cassava pipeline test
	$(PYTHON) tests/scripts/run_cassava_pipeline_test.py

test-cassava-clean: ## Run consolidated Cassava pipeline test with fresh database
	@echo "🧹 Running consolidated Cassava pipeline test with fresh database..."
	$(MAKE) db_reset
	$(MAKE) db_nuke
	$(MAKE) db_up
	$(MAKE) db_wait
	$(MAKE) migrate_up
	$(PYTHON) tests/scripts/run_cassava_pipeline_test.py

test-content-retrieval: ## Run content retrieval fallback chain test
	$(PYTHON) tests/scripts/run_content_retrieval_fallback_test.py

test-enhanced-content-retrieval: ## Run enhanced content retrieval fallback chain test
	$(PYTHON) tests/scripts/run_enhanced_content_retrieval_test.py

test-pmc-fix: ## Run PMC content retrieval fix test
	$(PYTHON) tests/scripts/run_pmc_content_fix_test.py

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

# ClinicalTrials.gov ingestion (use unified orchestrator instead)
SINCE ?= 2000-01-01
SINCE := $(or $(CTG_SINCE),$(SINCE))



# SEC data ingestion
SEC_JSON ?= data/sec/company_tickers_exchange.json
SEC_START ?= 1990-01-01

ingest_sec_tickers: ## Ingest SEC company tickers and securities (use SEC_JSON=path SEC_START=YYYY-MM-DD)
	$(PYTHON) scripts/ingest_sec.py tickers --json $(SEC_JSON) --start $(SEC_START)

ingest_sec_filings: ## Run SEC filings pipeline for daily monitoring
	$(PYTHON) scripts/ingest_sec.py filings

ingest_sec_backfill: ## Run SEC filings backfill (use START=YYYY-MM-DD END=YYYY-MM-DD)
ifndef START
	$(error Provide START=YYYY-MM-DD and END=YYYY-MM-DD for backfill)
endif
ifndef END
	$(error Provide END=YYYY-MM-DD for backfill)
endif
	$(PYTHON) scripts/ingest_sec.py backfill --start $(START) --end $(END)

ingest_sec_status: ## Check SEC pipeline status
	$(PYTHON) scripts/ingest_sec.py status

ingest_sec_all: ## Run all SEC ingestion tasks (tickers, filings, status)
	$(MAKE) ingest_sec_tickers
	$(MAKE) ingest_sec_filings
	$(MAKE) ingest_sec_status

# Resolver CLI commands
run_id: ## Generate run ID for tracking
	$(PYTHON) -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).strftime('resolver-%Y%m%dT%H%M%SZ'))"

resolve_one: ## Resolve single sponsor (use SPONSOR='company name')
	$(PYTHON) -m ncfd.mapping.cli resolve-one "$(SPONSOR)" --cfg config/resolver.yaml --k 25

resolve_batch: ## Resolve batch of sponsors
	$(PYTHON) -m ncfd.mapping.cli resolve-batch --cfg config/resolver.yaml --limit 25

resolve_one_persist: ## Resolve single sponsor and persist results (use SPONSOR='name' NCT=id RUN_ID=id)
	$(PYTHON) -m ncfd.mapping.cli resolve-one "$(SPONSOR)" --cfg config/resolver.yaml --k 25 --persist --nct $(NCT) --run-id $(RUN_ID)

# Review queue management
review_list: ## List items in review queue
	@$(PYTHON) -m ncfd.mapping.cli review-list

review_show: ## Show review queue item (use RQ=id)
	@$(PYTHON) -m ncfd.mapping.cli review-show $(RQ)

# Usage: make review_accept RQ=123 CID=6968 [APPLY=1]
review_accept: ## Accept review (use RQ=id CID=company_id [APPLY=1])
ifndef RQ
	$(error Provide RQ=<rq_id> and CID=<company_id>)
endif
ifndef CID
	$(error Provide CID=<company_id>)
endif
	@$(PYTHON) -m ncfd.mapping.cli review-accept $(RQ) --company-id $(CID) $(if $(APPLY),--apply-trial,)

# Usage: make review_reject RQ=123 [LABEL=1]
review_reject: ## Reject review (use RQ=id [LABEL=1])
ifndef RQ
	$(error Provide RQ=<rq_id>)
endif
	@$(PYTHON) -m ncfd.mapping.cli review-reject $(RQ) $(if $(LABEL),--label,)

# Batch processing
batch_dry: ## Run batch resolution in dry-run mode (use N=number)
	$(PYTHON) -m ncfd.mapping.cli resolve-batch --limit $(N) --cfg config/resolver.yaml

batch_persist: ## Run batch resolution and persist results (use N=number RUN_ID=id)
	$(PYTHON) -m ncfd.mapping.cli resolve-batch --limit $(N) --cfg config/resolver.yaml --persist --run-id $(RUN_ID) --apply-trial

# Subsidiaries processing
SINCE ?= 2018-01-01
LIM ?= 200

subs_inspect: ## Inspect subsidiary data
	@$(PYTHON) -m ncfd.ingest.subsidiaries inspect

subs_dry: ## Dry run subsidiary processing (use SINCE=YYYY-MM-DD LIM=number)
	@$(PYTHON) -m ncfd.ingest.subsidiaries dry --since $(SINCE) --limit $(LIM)

subs_load: ## Load subsidiary data (use SINCE=YYYY-MM-DD LIM=number)
	@$(PYTHON) -m ncfd.ingest.subsidiaries load --since $(SINCE) --limit $(LIM)

subs_build: ## Alias for subs_load (kept for compatibility)
	$(MAKE) subs_load

subs_link: ## Link subsidiaries (use LIM=number)
	@$(PYTHON) -m ncfd.ingest.subs_link dry --limit $(LIM)

subs_link_load: ## Load subsidiary links
	@$(PYTHON) -m ncfd.ingest.subs_link load

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

	$(MAKE) ingest_sec_tickers

# --- Legacy Aliases (for backward compatibility) ---
.PHONY: db_migrate db.psql db.psql.c db.logs db.status db.dump db.dump.schema db.restore db.health db.env

# Legacy database commands (kept for compatibility)
db_migrate: ## Legacy: Create and run auto-generated migration
	POSTGRES_DSN=$(POSTGRES_DSN) DATABASE_URL=$(DATABASE_URL) $(VENV)/bin/alembic revision --autogenerate -m "auto"
	$(MAKE) migrate_up
# Batch resolve trials using auto-decider (recommended for production)
resolve_batch_auto: ## Resolve batch of trials using auto-decider cascade
	@echo "🚀 Starting batch resolution with auto-decider..."
	@echo "   - Deterministic → Probabilistic → LLM (if needed)"
	@echo "   - Processing $(or $(N),100) trials..."
	@echo "   - Run ID: $$(date -u +%Y%m%dT%H%M%SZ)"
	@RUN_ID=$$(date -u +%Y%m%dT%H%M%SZ); \
	echo "RUN_ID=$$RUN_ID"; \
	$(PYTHON) -m ncfd.mapping.cli resolve-batch \
		--limit $(or $(N),100) \
		--persist \
		--apply-trial \
		--run-id "$$RUN_ID" \
		--decider auto

# Quick batch with smaller limit (for testing)
resolve_batch_auto_test: ## Resolve small batch for testing
	$(MAKE) resolve_batch_auto N=25

# Large batch for production runs
resolve_batch_auto_prod: ## Resolve large batch for production
	$(MAKE) resolve_batch_auto N=500

# Batch with custom limit
resolve_batch_auto_custom: ## Resolve batch with custom limit (use N=number)
ifndef N
	$(error Provide N=<number> for custom batch size)
endif
	$(MAKE) resolve_batch_auto N=$(N)

# Historical Universe Backtest Commands
INDICATION ?= Alzheimer
START_DATE ?= 2018-01-01
END_DATE ?= 2023-12-31

universe_backtest: ## Run complete historical universe backtest (use INDICATION=disease START_DATE=YYYY-MM-DD END_DATE=YYYY-MM-DD)
	$(PYTHON) scripts/universe_pipeline.py --indication "$(INDICATION)" --start-date "$(START_DATE)" --end-date "$(END_DATE)"

universe_example: ## Run example backtest for Alzheimer's trials
	$(PYTHON) examples/universe_backtest_example.py --mode full

# E2E Testing
.PHONY: e2e e2e-docker e2e-system e2e-quick e2e-full e2e-cost-min e2e-mock test-e2e test-e2e-live

# Real E2E Pipeline (NEW - uses actual system components)
e2e: ## Real end-to-end pipeline execution (CT.gov -> SEC -> PubMed -> Study Cards -> Evaluation)
	$(PYTHON) scripts/e2e_run.py \
		--config config/e2e.yaml \
		--max-trials 5 \
		--at-least-study-cards 1 \
		--time-budget-seconds 900 \
		--log-file logs/e2e_run.log \
		--report-dir reports/ \
		--log-level INFO

e2e-docker: ## Real E2E pipeline inside Docker container  
	$(COMPOSE) exec app python scripts/e2e_run.py \
		--config config/e2e.yaml \
		--max-trials 5 \
		--at-least-study-cards 1 \
		--time-budget-seconds 900 \
		--log-file logs/e2e_run.log \
		--report-dir reports/ \
		--log-level INFO

e2e-debug: ## Real E2E with debug logging and longer timeout
	$(PYTHON) scripts/e2e_run.py \
		--config config/e2e.yaml \
		--max-trials 3 \
		--at-least-study-cards 1 \
		--time-budget-seconds 1800 \
		--log-file logs/e2e_debug.log \
		--report-dir reports/ \
		--log-level DEBUG

e2e-force-full: ## Real E2E with force full scan (ignores incremental state)
	$(PYTHON) scripts/e2e_run.py \
		--config config/e2e.yaml \
		--max-trials 5 \
		--at-least-study-cards 1 \
		--time-budget-seconds 900 \
		--log-file logs/e2e_full_scan.log \
		--report-dir reports/ \
		--log-level INFO \
		--force-full-scan

# Legacy E2E Tests (keep for compatibility)
e2e-mock: ## Mock E2E test (zero cost, ~1 second, perfect for CI/CD)
	DATABASE_URL=$(DATABASE_URL) $(PYTHON) scripts/run_system_e2e_mock.py \
		--max-trials 5 --pubmed-max 10 --sec-ciks 1682852 \
		--assets Keytruda --indications cancer --enable-synthesis

e2e-cost-min: ## Cost-minimized E2E test (~$0.10, ~1-2 minutes)
	DATABASE_URL=$(DATABASE_URL) $(PYTHON) scripts/run_system_e2e_cost_min.py \
		--since-days 7 --max-trials 5 --pubmed-max 10 \
		--sec-ciks 1682852 --assets Keytruda --indications cancer \
		--max-cost 0.50

e2e-quick: ## Quick E2E test (small scope, ~$1-2, ~2-3 minutes)
	DATABASE_URL=$(DATABASE_URL) $(PYTHON) scripts/run_system_e2e.py \
		--since-days 30 --max-trials 10 --pubmed-max 20 \
		--sec-ciks 1682852 --assets Keytruda --indications cancer

e2e-system: ## Standard E2E test (medium scope, ~$3-5, ~5-10 minutes)
	DATABASE_URL=$(DATABASE_URL) $(PYTHON) scripts/run_system_e2e.py \
		--since-days 90 --max-trials 50 --pubmed-max 100 \
		--sec-ciks 1682852 813672 --assets Keytruda Pembrolizumab \
		--indications cancer melanoma

e2e-full: ## Full E2E with synthesis (large scope, ~$10-20, ~10-15 minutes)
	DATABASE_URL=$(DATABASE_URL) $(PYTHON) scripts/run_system_e2e.py \
		--since-days 90 --max-trials 50 --pubmed-max 100 \
		--sec-ciks 1682852 813672 --assets Keytruda Pembrolizumab \
		--indications cancer melanoma --synthesize-auto 3

test-e2e: ## Run pytest E2E tests (unit tests only)
	$(PYTHON) -m pytest -m e2e -v --tb=short

test-e2e-live: ## Run E2E tests with live services (requires NCFD_E2E_LIVE=1)
	NCFD_E2E_LIVE=1 $(PYTHON) -m pytest -m e2e -v --tb=short

test-e2e-all: ## Run all E2E tests including live services
	$(PYTHON) -m pytest -m e2e -v --tb=short
	NCFD_E2E_LIVE=1 $(PYTHON) -m pytest -m e2e -v --tb=short

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


setup-db: ## Setup test database with required PostgreSQL extensions
	@echo "🔧 Setting up test database with required extensions..."
	$(PYTHON) scripts/setup_test_database.py
