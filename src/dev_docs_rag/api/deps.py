"""FastAPI dependencies shared by the routes."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session_factory
from ..services.cache import RedisCache
from ..services.embeddings import Embedder, FastEmbedEmbedder


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a database session for the duration of a request."""
    async with get_session_factory()() as session:
        yield session


def get_cache(request: Request) -> RedisCache:
    """Return the cache created during application startup."""
    return request.app.state.cache


def get_embedder(request: Request) -> Embedder:
    """Return the embedder, loading the model on the first search request."""
    embedder = getattr(request.app.state, "embedder", None)
    if embedder is None:
        settings = get_settings()
        embedder = FastEmbedEmbedder(
            model_name=settings.embedding_model,
            dim=settings.embedding_dim,
            batch_size=settings.embedding_batch_size,
        )
        request.app.state.embedder = embedder
    return embedder
