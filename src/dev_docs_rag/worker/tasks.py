"""Celery tasks for knowledge indexing."""

import asyncio
from dataclasses import asdict

from celery.exceptions import Reject

from ..config import get_settings
from ..db import build_engine, build_session_factory
from ..services.embeddings import Embedder, FastEmbedEmbedder
from ..services.ingest import FileStats, IngestionError, TransientIngestionError, index_document
from .celery_app import celery_app

_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Return the process-wide embedder, loading the model on first use."""
    global _embedder
    if _embedder is None:
        settings = get_settings()
        _embedder = FastEmbedEmbedder(
            model_name=settings.embedding_model,
            dim=settings.embedding_dim,
            batch_size=settings.embedding_batch_size,
        )
    return _embedder


@celery_app.task(bind=True, name="dev_docs_rag.worker.tasks.index_file")
def index_file(self, relative_path: str) -> dict[str, object]:
    """Index one knowledge file; retry transient failures and dead-letter permanent ones."""
    settings = get_settings()
    try:
        return asdict(asyncio.run(_index(relative_path)))
    except TransientIngestionError as exc:
        if self.request.retries < settings.ingestion_max_retries:
            raise self.retry(exc=exc, countdown=2**self.request.retries) from exc
        raise Reject(f"retries exhausted: {exc}", requeue=False) from exc
    except IngestionError as exc:
        raise Reject(str(exc), requeue=False) from exc
    except Exception as exc:
        if self.request.retries < settings.ingestion_max_retries:
            raise self.retry(exc=exc, countdown=2**self.request.retries) from exc
        raise Reject(str(exc), requeue=False) from exc


async def _index(relative_path: str) -> FileStats:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    try:
        return await index_document(
            relative_path,
            session_factory=build_session_factory(engine),
            embedder=get_embedder(),
            settings=settings,
        )
    finally:
        await engine.dispose()
