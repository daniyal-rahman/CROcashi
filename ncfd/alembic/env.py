# alembic/env.py
import os, sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

<<<<<<< HEAD
# --- add src/ to sys.path and import your models' Base
THIS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, ".."))   # .../ncfd
SRC_ROOT = os.path.join(PROJECT_ROOT, "src")                   # .../ncfd/src
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)
=======
import sys
from pathlib import Path

# Ensure the ``src`` directory is on the path so that models can be imported.
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / "src"))

from ncfd.db.models import Base  # noqa: E402

# target metadata for autogeneration
target_metadata = Base.metadata
>>>>>>> origin/main

from ncfd.db.models import Base  # <-- make sure models.py defines Base and tables
target_metadata = Base.metadata

# If URL not in alembic.ini, allow DATABASE_URL env
if not config.get_main_option("sqlalchemy.url"):
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
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
