PY?=python3
VENV=.venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python

.PHONY: setup fmt lint type test db_migrate ingest_ctgov run_all alembic_init

setup:
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e .[dev]
	$(VENV)/bin/pre-commit install
	@echo "✅ venv ready. Activate with: source $(VENV)/bin/activate"

fmt:
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/black .

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/black --check .

type:
	$(VENV)/bin/mypy src

test:
	CONFIG_PROFILE=local $(VENV)/bin/pytest -q

alembic_init:
	@# one-time (if you haven't created migrations folder)
	$(VENV)/bin/alembic init alembic

db_migrate:
	@# generate new revision from models (edit message as needed)
	$(VENV)/bin/alembic revision --autogenerate -m "auto"
	@# apply latest migrations
	$(VENV)/bin/alembic upgrade head

ingest_ctgov:
	CONFIG_PROFILE=local $(PYTHON) scripts/ingest_ctgov.py --since 2000-01-01

# --- Dockerized DB ---
COMPOSE = docker compose
DC_DIR  = .
DB_SVC  = db

# export $(shell sed -n 's/^\([^#][^=]*\)=.*/\1/p' .env > /dev/null 2>&1; cat .env | sed -n 's/^\([^#][^=]*\)=.*/\1/p')
# Load .env into make vars and export them to subprocesses (docker/alembic/pytest)
ifneq (,$(wildcard .env))
include .env
# Export only keys that look like env var names; no parentheses → safe for $(shell ...)
export $(shell awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/{print $$1}' .env)
endif

db_up:
	$(COMPOSE) -f docker-compose.yml up -d $(DB_SVC)

db_down:
	$(COMPOSE) -f docker-compose.yml down

db_nuke:
	$(COMPOSE) -f docker-compose.yml down -v

db_logs:
	$(COMPOSE) -f docker-compose.yml logs -f $(DB_SVC)

db_wait:
	@echo "Waiting for Postgres to be healthy..."
	@for i in $$(seq 1 60); do \
		STATUS=$$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' ncfd_db 2>/dev/null); \
		if [ "$$STATUS" = "healthy" ]; then \
			echo "Postgres healthy ✅"; exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "Postgres failed to become healthy ❌"; docker ps; exit 1

db_psql:
	docker exec -it ncfd_db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

# --- Alembic helpers ---
migrate_up:
	DATABASE_URL=${DATABASE_URL} alembic upgrade head

migrate_down_one:
	DATABASE_URL=${DATABASE_URL} alembic downgrade -1

alembic:
	DATABASE_URL=${DATABASE_URL} alembic $(ARGS)

run_all:
	make db_migrate
	make ingest_ctgov
