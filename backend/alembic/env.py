"""Alembic environment.

The URL comes from application settings, and the async driver is stripped for
migrations so Alembic can run synchronously (asyncpg -> psycopg / aiosqlite ->
sqlite3). Autogenerate targets ``Base.metadata``.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app import models  # noqa: E402,F401  (import registers every mapper)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_SYNC_DRIVERS = {
    "postgresql+asyncpg": "postgresql+psycopg2",
    "sqlite+aiosqlite": "sqlite",
}


def sync_url() -> str:
    url = settings.database_url
    for async_prefix, sync_prefix in _SYNC_DRIVERS.items():
        if url.startswith(async_prefix):
            return url.replace(async_prefix, sync_prefix, 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = sync_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
