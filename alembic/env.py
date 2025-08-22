# alembic/env.py
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Ensure src/ is on sys.path so we can import the application package
THIS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, ".."))   # .../CROcashi
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")                   # .../CROcashi/src
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from ncfd.db.models import Base  # noqa: E402
target_metadata = Base.metadata

# If URL not set in alembic.ini, allow DATABASE_URL
if not config.get_main_option("sqlalchemy.url"):
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)
    else:
        raise RuntimeError("Set sqlalchemy.url in alembic.ini or DATABASE_URL")
import os
db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)


def _resolve_db_url():
    # 1) Prefer real env var (works with `DATABASE_URL=... alembic upgrade head`)
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    # 2) Fall back to alembic.ini value
    ini_url = config.get_main_option("sqlalchemy.url")

    # If ini value looks like ${SOME_ENV}, try to expand it
    if ini_url and ini_url.startswith("${") and ini_url.endswith("}"):
        env_name = ini_url[2:-1]
        return os.getenv(env_name)

    return ini_url

def run_migrations_offline() -> None:
    url = _resolve_db_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set and sqlalchemy.url is empty")

    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = url

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _resolve_db_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not set and sqlalchemy.url is empty")

    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
