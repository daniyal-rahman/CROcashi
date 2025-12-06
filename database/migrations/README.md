# Database Migrations

This directory contains Alembic migration files for the biotech knowledge graph database.

## Usage

### Create a new migration

```bash
alembic revision --autogenerate -m "description of changes"
```

### Apply migrations

```bash
alembic upgrade head
```

### Rollback migrations

```bash
alembic downgrade -1  # Rollback one version
alembic downgrade base  # Rollback all migrations
```

### View migration history

```bash
alembic history
alembic current
```

