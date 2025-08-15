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

run_all:
	make db_migrate
	make ingest_ctgov
