"""Synchronous SQLAlchemy engine for the legacy synchronous stores.

The application uses an async engine (aiosqlite) for request-path and agent
code.  The notification stores (device tokens, alerts) expose a synchronous
interface consumed by sync FastAPI routes and the price checker, so they are
backed by a separate *synchronous* engine pointing at the same SQLite file.

SQLite serialises access at the file level, so the two engines coexist safely
under the single-user hackathon load.  The schema is created by the async
engine at startup; this module only opens sessions.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_session_factory: sessionmaker[Session] | None = None


def _sync_url(database_url: str) -> str:
    """Convert an async DB URL to its synchronous driver equivalent."""
    return (
        database_url
        .replace("+aiosqlite", "")
        .replace("+asyncpg", "")
        .replace("postgresql+psycopg", "postgresql")
    )


def init_sync_db(database_url: str, *, echo: bool = False) -> None:
    global _engine, _session_factory
    if _engine is not None:
        return
    _engine = create_engine(_sync_url(database_url), echo=echo, future=True)
    _session_factory = sessionmaker(_engine, expire_on_commit=False, class_=Session)


def get_sync_session() -> Session:
    if _session_factory is None:
        raise RuntimeError("Sync database not initialised — call init_sync_db() first")
    return _session_factory()


def create_all_sync() -> None:
    """Create all tables on the sync engine.

    Production relies on the async engine for schema creation; this helper is
    used by unit tests that exercise the sync stores against a fresh file.
    """
    from backend.app.persistence.models import Base

    if _engine is None:
        raise RuntimeError("Sync database not initialised — call init_sync_db() first")
    Base.metadata.create_all(_engine)


def reset_sync_db() -> None:
    """Dispose the sync engine (used in tests and shutdown)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
