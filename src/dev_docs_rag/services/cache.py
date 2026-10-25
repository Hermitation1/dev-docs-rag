"""Redis cache for search responses and query embeddings.

Redis is an optimisation, never a dependency: every method swallows connection
errors so a dead cache only costs latency, not availability.
"""

import hashlib
import json
import logging
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def search_cache_key(
    *,
    model: str,
    index_version: int,
    project: str | None,
    library: str | None,
    version: str | None,
    status: str,
    top_k: int,
    query: str,
) -> str:
    """Build a key that changes when the index version or the model changes."""
    payload = f"{query.strip().lower()}|{project}|{library}|{version}|{status}|{top_k}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return f"search:{model}:{index_version}:{digest}"


def embedding_cache_key(*, model: str, query: str) -> str:
    """Build a key for a cached query embedding."""
    digest = hashlib.sha1(query.strip().lower().encode("utf-8")).hexdigest()
    return f"embed:{model}:{digest}"


class RedisCache:
    """Async Redis wrapper with JSON serialisation and graceful degradation."""

    def __init__(self, url: str, ttl_seconds: int) -> None:
        """Connect lazily and remember the TTL for cached values."""
        self._redis = Redis.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds

    async def get_json(self, key: str) -> Any | None:
        """Return a cached JSON value or ``None`` on a miss or a dead cache."""
        try:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw is not None else None
        except (RedisError, ValueError) as exc:
            logger.warning("cache read failed: %s", exc)
            return None

    async def set_json(self, key: str, value: Any) -> None:
        """Store a JSON-serialisable value with the configured TTL."""
        try:
            await self._redis.set(key, json.dumps(value), ex=self._ttl)
        except RedisError as exc:
            logger.warning("cache write failed: %s", exc)

    async def get_vector(self, key: str) -> list[float] | None:
        """Return a cached embedding vector."""
        value = await self.get_json(key)
        return value if isinstance(value, list) else None

    async def set_vector(self, key: str, vector: list[float]) -> None:
        """Cache an embedding vector."""
        await self.set_json(key, vector)

    async def ping(self) -> bool:
        """Check that Redis answers."""
        try:
            return bool(await self._redis.ping())
        except RedisError:
            return False

    async def close(self) -> None:
        """Release the underlying connection pool."""
        await self._redis.aclose()
