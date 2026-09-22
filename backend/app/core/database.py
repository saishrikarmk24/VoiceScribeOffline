"""Async SQLAlchemy engine/session management.

PostgreSQL is the target database. When it is unreachable (a very common case on
a workstation without Postgres installed) and ``ALLOW_SQLITE_FALLBACK`` is set,
the application transparently switches to a local SQLite file so the prototype
still runs end to end. The active backend is reported on ``/api/health``.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all MedScribe models."""


class DatabaseState:
    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self.active_url: str | None = None
        self.dialect: str = "unknown"
        self.using_fallback: bool = False
        self.last_error: str | None = None

    @property
    def ready(self) -> bool:
        return self.session_factory is not None


db_state = DatabaseState()


def _engine_kwargs(url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"echo": settings.db_echo, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
    return kwargs


def _configure_sqlite(engine: AsyncEngine) -> None:
    """WAL plus a busy timeout so the live pipeline and API requests can both write.

    Without this, a background structuring pass and an incoming request race for
    the single SQLite writer lock and one of them fails immediately.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pragma: no cover - driver callback
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


async def _try_connect(url: str) -> AsyncEngine:
    engine = create_async_engine(url, **_engine_kwargs(url))
    if url.startswith("sqlite"):
        _configure_sqlite(engine)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return engine


def _sanitize(url: str) -> str:
    """Strip credentials before logging or exposing a connection string."""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    _, _, host = rest.partition("@")
    return f"{scheme}://***@{host}"


async def init_database(create_schema: bool | None = None, url: str | None = None) -> DatabaseState:
    """Connect to the database, falling back to SQLite when configured."""
    target = url or settings.database_url
    engine: AsyncEngine | None = None
    try:
        engine = await _try_connect(target)
        db_state.using_fallback = False
    except Exception as exc:  # pragma: no cover - depends on local environment
        db_state.last_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "primary_database_unavailable",
            extra={"database_url": _sanitize(target), "error": db_state.last_error},
        )
        if not settings.allow_sqlite_fallback:
            raise
        target = settings.sqlite_fallback_url
        engine = await _try_connect(target)
        db_state.using_fallback = True
        logger.warning("using_sqlite_fallback", extra={"database_url": target})

    db_state.engine = engine
    db_state.active_url = target
    db_state.dialect = engine.dialect.name
    db_state.session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    should_create = settings.auto_create_schema if create_schema is None else create_schema
    if should_create:
        from app import models  # noqa: F401  (registers mappers)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Handle lightweight SQLite schema migrations for new columns
        if engine.dialect.name == "sqlite":
            await _migrate_sqlite_schema(engine)

        logger.info("schema_ready", extra={"dialect": db_state.dialect})

    return db_state


async def _migrate_sqlite_schema(engine: AsyncEngine) -> None:
    """Ensure newly added columns exist in existing SQLite database files."""
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(users)"))
        existing_cols = {row[1] for row in result.fetchall()}
        if existing_cols:
            migrations = [
                ("doctor_id", "ALTER TABLE users ADD COLUMN doctor_id VARCHAR(64)"),
                ("department", "ALTER TABLE users ADD COLUMN department VARCHAR(128)"),
                ("password_hash", "ALTER TABLE users ADD COLUMN password_hash VARCHAR(256)"),
                ("created_by", "ALTER TABLE users ADD COLUMN created_by VARCHAR(128)"),
                ("last_login_at", "ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP"),
            ]
            for col_name, sql in migrations:
                if col_name not in existing_cols:
                    try:
                        await conn.execute(text(sql))
                        logger.info("sqlite_column_added", extra={"column": col_name})
                    except Exception as exc:
                        logger.warning("sqlite_migration_skipped", extra={"column": col_name, "error": str(exc)})

        # Ensure sessions table has newly added columns in existing database files
        result_sessions = await conn.execute(text("PRAGMA table_info(sessions)"))
        existing_session_cols = {row[1] for row in result_sessions.fetchall()}
        if existing_session_cols:
            session_migrations = [
                ("patient_name", "ALTER TABLE sessions ADD COLUMN patient_name VARCHAR(255)"),
                ("doctor_name", "ALTER TABLE sessions ADD COLUMN doctor_name VARCHAR(255)"),
                ("faculty_name", "ALTER TABLE sessions ADD COLUMN faculty_name VARCHAR(255)"),
                ("audio_source", "ALTER TABLE sessions ADD COLUMN audio_source VARCHAR(32) DEFAULT 'MICROPHONE'"),
            ]
            for col_name, sql in session_migrations:
                if col_name not in existing_session_cols:
                    try:
                        await conn.execute(text(sql))
                        logger.info("sqlite_column_added", extra={"table": "sessions", "column": col_name})
                    except Exception as exc:
                        logger.warning("sqlite_migration_skipped", extra={"table": "sessions", "column": col_name, "error": str(exc)})


async def dispose_database() -> None:
    if db_state.engine is not None:
        await db_state.engine.dispose()
    db_state.engine = None
    db_state.session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if db_state.session_factory is None:
        raise RuntimeError("Database is not initialised. Call init_database() first.")
    return db_state.session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def health() -> dict[str, Any]:
    info = {
        "connected": False,
        "dialect": db_state.dialect,
        "using_fallback": db_state.using_fallback,
        "url": _sanitize(db_state.active_url or settings.database_url),
    }
    if db_state.engine is None:
        info["error"] = db_state.last_error or "not initialised"
        return info
    try:
        async with db_state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        info["connected"] = True
    except Exception as exc:  # pragma: no cover
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info
