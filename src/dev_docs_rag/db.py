"""Async database engine and session factory.

The engine is a per-process singleton: created lazily, reset after a Celery
fork so the child never reuses the parent's asyncpg connections.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def build_engine(database_url: str) -> AsyncEngine:
    """Create an async engine with liveness checks enabled."""
    return create_async_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory that keeps loaded attributes after commit."""
    return async_sessionmaker(engine, expire_on_commit=False)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, creating it on first use."""
    global _engine, _session_factory
    if _session_factory is None:
        _engine = build_engine(get_settings().database_url)
        _session_factory = build_session_factory(_engine)
    return _session_factory


def reset_engine() -> None:
    """Drop cached engine references without touching already-open connections."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


async def dispose_engine() -> None:
    """Close the connection pool and forget the engine."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
    reset_engine()
