"""FastAPI application factory and health endpoint."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import text

from ..config import get_settings
from ..db import dispose_engine, get_session_factory
from ..models import EMBEDDING_DIM
from ..services.cache import RedisCache
from ..worker.celery_app import celery_app
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create shared resources on startup and release them on shutdown."""
    settings = get_settings()
    if settings.embedding_dim != EMBEDDING_DIM:
        raise RuntimeError(
            f"EMBEDDING_DIM={settings.embedding_dim} does not match the schema dimension "
            f"{EMBEDDING_DIM}. Change the model, add a migration and run a reindex."
        )
    app.state.cache = RedisCache(settings.redis_url, settings.cache_ttl_seconds)
    get_session_factory()
    yield
    await app.state.cache.close()
    await dispose_engine()


def _broker_alive() -> bool:
    """Check that RabbitMQ accepts a connection."""
    try:
        with celery_app.connection_for_read() as connection:
            connection.ensure_connection(max_retries=1, timeout=2)
        return True
    except Exception:
        return False


def create_app() -> FastAPI:
    """Build the ASGI application with its routes."""
    app = FastAPI(title="Dev-Docs RAG", version="0.2.0", lifespan=lifespan)
    app.include_router(router)

    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        """Report dependencies. Postgres is required; Redis and RabbitMQ are optional for search."""
        session_factory = get_session_factory()
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"postgres": "down"}) from exc

        redis_ok = await request.app.state.cache.ping()
        broker_ok = await asyncio.to_thread(_broker_alive)
        return {
            "status": "ok" if redis_ok and broker_ok else "degraded",
            "postgres": "ok",
            "redis": "ok" if redis_ok else "down",
            "rabbitmq": "ok" if broker_ok else "down",
        }

    return app


app = create_app()
