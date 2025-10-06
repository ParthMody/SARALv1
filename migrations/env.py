# migrations/env.py
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

# Ensure repo root is on path (so "from app..." works when running alembic at repo root)
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Load .env so DATABASE_URL is available
load_dotenv()

# Import your app metadata AFTER sys.path & dotenv
from app.db import Base
from sqlalchemy import create_engine

# --------------------------------------------------------------------
# Alembic Config
# --------------------------------------------------------------------
config = context.config

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the app's models metadata for autogenerate
target_metadata = Base.metadata

# Derive DB URL from env if present, otherwise fall back to alembic.ini
database_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if not database_url:
    raise RuntimeError("DATABASE_URL not set and sqlalchemy.url missing in alembic.ini")

# Make sure alembic sees the effective URL (shows up in revision headers)
config.set_main_option("sqlalchemy.url", database_url)

# SQLite detection (affects batch mode below)
is_sqlite = database_url.startswith("sqlite")

# --------------------------------------------------------------------
# Offline mode
# --------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations without a DBAPI connection."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=is_sqlite,  # needed for SQLite schema changes
    )

    with context.begin_transaction():
        context.run_migrations()

# --------------------------------------------------------------------
# Online mode
# --------------------------------------------------------------------
def run_migrations_online() -> None:
    """Run migrations with a real connection."""
    # Use the same URL Alembic knows about (keeps .ini and .env aligned)
    connectable: Engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()

# --------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
