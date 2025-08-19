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
	POSTGRES_DSN=${POSTGRES_DSN} alembic upgrade head

migrate_down_one:
	POSTGRES_DSN=${POSTGRES_DSN} alembic downgrade -1

alembic:
	POSTGRES_DSN=${POSTGRES_DSN} alembic $(ARGS)

run-id:
	python -c "from ncfd.utils.run_id import make_run_id; print(make_run_id())"

resolve-one:
	 PYTHONPATH=ncfd/src python -m ncfd.mapping.cli resolve-one "$(SPONSOR)" --cfg config/resolver.yaml --k 25

resolve-batch:
	 PYTHONPATH=ncfd/src python -m ncfd.mapping.cli resolve-batch --cfg config/resolver.yaml --limit 25

resolve-one-persist:
	PYTHONPATH=ncfd/src python -m ncfd.mapping.cli resolve-one "$(SPONSOR)" --cfg config/resolver.yaml --k 25 --persist --nct $(NCT) --run-id $(RUN_ID)

review-list:
	@PYTHONPATH=ncfd/src python -m ncfd.mapping.cli review-list

review-show:
	@PYTHONPATH=ncfd/src python -m ncfd.mapping.cli review-show $(RQ)

review-accept:
	@PYTHONPATH=ncfd/src python -m ncfd.mapping.cli review-accept $(RQ) --apply-trial

review-reject:
	@PYTHONPATH=ncfd/src python -m ncfd.mapping.cli review-reject $(RQ)

batch-dry:
	PYTHONPATH=ncfd/src python -m ncfd.mapping.cli resolve-batch --limit $(N) --cfg config/resolver.yaml

batch-persist:
	PYTHONPATH=ncfd/src python -m ncfd.mapping.cli resolve-batch --limit $(N) --cfg config/resolver.yaml --persist --run-id $(RUN_ID) --apply-trial

# Subsidiaries (Ex-21)
SINCE ?= 2018-01-01
LIM   ?= 200

subs-inspect:
	@PYTHONPATH=ncfd/src python -m ncfd.ingest.subsidiaries inspect

subs-dry:
	@PYTHONPATH=ncfd/src python -m ncfd.ingest.subsidiaries dry --since $(SINCE) --limit $(LIM)

subs-load:
	@PYTHONPATH=ncfd/src python -m ncfd.ingest.subsidiaries load --since $(SINCE) --limit $(LIM)

# keep old name working if you had it
subs-build: subs-load

# backward-compat alias
subs-build: subs-load

subs-link:
	python -m ncfd.ingest.subs_link dry --limit $${LIM:-50}

subs-link-load:
	python -m ncfd.ingest.subs_link load

run_all:
	make db_migrate
	make ingest_ctgov
