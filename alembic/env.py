"""Alembic migration environment."""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Allow `import db` from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env (optional; safe if missing)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

config = context.config

# Resolve DATABASE_URL from env (override alembic.ini)
_db_url = os.getenv("DATABASE_URL", "").strip()
if _db_url:
    # psycopg2 driver
    if _db_url.startswith("postgres://"):
        _db_url = "postgresql+psycopg2://" + _db_url[len("postgres://"):]
    elif _db_url.startswith("postgresql://") and "+psycopg2" not in _db_url:
        _db_url = "postgresql+psycopg2://" + _db_url[len("postgresql://"):]
    config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We don't use SQLAlchemy ORM — pure SQL migrations.
target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
