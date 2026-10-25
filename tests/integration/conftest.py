"""Fixtures for integration tests: a real database, Redis and the app."""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dev_docs_rag.api.app import create_app
from dev_docs_rag.config import get_settings
from dev_docs_rag.db import get_session_factory
from dev_docs_rag.models import Chunk, Document
from dev_docs_rag.services.cache import RedisCache
from dev_docs_rag.services.chunking import build_embedding_text, estimate_tokens
from dev_docs_rag.services.embeddings import FakeEmbedder

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


def _ensure_database(url: str) -> None:
    prefix, _, name = url.rpartition("/")
    database = name.split("?")[0]
    maintenance = f"{prefix}/postgres".replace("postgresql+asyncpg://", "postgresql://")

    async def create() -> None:
        connection = None
        for attempt in range(30):
            try:
                connection = await asyncpg.connect(maintenance)
                break
            except (OSError, asyncpg.PostgresError):
                if attempt == 29:
                    raise
                await asyncio.sleep(1)
        assert connection is not None
        try:
            exists = await connection.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", database
            )
            if not exists:
                await connection.execute(f'CREATE DATABASE "{database}"')
        finally:
            await connection.close()

    asyncio.run(create())


@pytest.fixture(scope="session", autouse=True)
def prepared_database() -> Iterator[None]:
    """Create the test database and apply migrations once per session."""
    _ensure_database(TEST_DATABASE_URL)
    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture(autouse=True)
def knowledge_dir(tmp_path, monkeypatch):
    """Point the service at a throwaway knowledge directory."""
    root = tmp_path / "knowledge"
    root.mkdir()
    monkeypatch.setattr(get_settings(), "knowledge_dir", root)
    return root


@pytest_asyncio.fixture(autouse=True)
async def clean_state(prepared_database: None) -> AsyncIterator[None]:
    """Empty the tables and the cache around every test."""
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis.flushdb()
    yield
    async with get_session_factory()() as session:
        await session.execute(text("TRUNCATE chunks, documents RESTART IDENTITY CASCADE"))
        await session.execute(text("UPDATE index_state SET version = 0"))
        await session.commit()
    await redis.flushdb()
    await redis.aclose()


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Yield a session bound to the test database."""
    async with get_session_factory()() as session:
        yield session


@pytest_asyncio.fixture
async def app():
    """Build the app with fake embeddings and no lifespan side effects."""
    application = create_app()
    settings = get_settings()
    application.state.cache = RedisCache(settings.redis_url, settings.cache_ttl_seconds)
    application.state.embedder = FakeEmbedder(dim=settings.embedding_dim)
    yield application
    await application.state.cache.close()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    """HTTP client that talks to the app in-process."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def enqueued(monkeypatch) -> list[str]:
    """Capture Celery enqueues instead of talking to RabbitMQ."""
    calls: list[str] = []

    def fake_delay(relative_path: str) -> None:
        calls.append(relative_path)

    monkeypatch.setattr("dev_docs_rag.api.routes.index_file.delay", fake_delay)
    return calls


@pytest_asyncio.fixture
async def seed_document(session: AsyncSession) -> Callable[..., Awaitable[Document]]:
    """Insert one document and its chunks, embedded with FakeEmbedder."""
    embedder = FakeEmbedder(dim=get_settings().embedding_dim)

    async def seed(
        *,
        library: str = "fastapi",
        version: str = "master",
        heading: str = "Tutorial",
        texts: tuple[str, ...] = ("Use the lifespan handler.",),
        path: str = "docs/guide.md",
        status: str = "approved",
        project: str | None = None,
    ) -> Document:
        document = Document(
            project=project,
            library=library,
            version=version,
            path=path,
            source_url=f"https://example.com/repo/blob/{version}/{path}",
            tier="own" if project else "official",
            type="doc",
            status=status,
            needs_review=False,
            license="MIT",
            content_hash="0" * 64,
            fetched_at=datetime.now(UTC).date(),
            indexed_at=datetime.now(UTC),
        )
        session.add(document)
        await session.flush()

        vectors = embedder.embed_documents(
            [
                build_embedding_text(
                    library=library, version=version, heading_path=heading, text=body
                )
                for body in texts
            ]
        )
        for position, (body, vector) in enumerate(zip(texts, vectors, strict=True)):
            session.add(
                Chunk(
                    document_id=document.id,
                    ord=position,
                    heading_path=heading,
                    text=body,
                    token_count=estimate_tokens(body),
                    embedding=vector,
                    embedding_model=embedder.model_name,
                )
            )
        await session.commit()
        return document

    return seed
