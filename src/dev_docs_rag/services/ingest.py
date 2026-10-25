"""Index one knowledge document at a time."""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..models import Chunk, Document, DocumentStatus, IndexState
from .chunking import build_embedding_text, chunk_markdown
from .embeddings import Embedder
from .knowledge import KnowledgeDocument, read_document

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Permanent failure: retrying the same input will not help."""


class TransientIngestionError(Exception):
    """Temporary failure such as a network problem: retrying may help."""


@dataclass(frozen=True)
class FileStats:
    """How much work one file produced."""

    path: str
    chunks: int
    skipped: bool


def _fingerprint(document: KnowledgeDocument, model: str) -> str:
    """Hash everything that affects the stored document, including the embedding model.

    A document is current only when its body, metadata and embedding model all match,
    so changing the model or a trust flag forces a reindex instead of a silent skip.
    """
    payload = {
        "body": document.body,
        "project": document.project,
        "library": document.library,
        "version": document.version,
        "source_url": document.source_url,
        "tier": document.tier,
        "type": document.type,
        "status": document.status,
        "needs_review": document.needs_review,
        "license": document.license,
        "fetched_at": document.fetched_at.isoformat() if document.fetched_at else None,
        "embedding_model": model,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def index_document(
    relative_path: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    settings: Settings,
) -> FileStats:
    """Chunk, embed and store one knowledge document, replacing its previous version."""
    document = await _read(relative_path)
    content_hash = _fingerprint(document, embedder.model_name)

    async with session_factory() as session:
        project_filter = (
            Document.project.is_(None)
            if document.project is None
            else Document.project == document.project
        )
        existing = await session.scalar(
            select(Document).where(
                project_filter,
                Document.library == document.library,
                Document.version == document.version,
                Document.path == document.path,
            )
        )
        if existing is not None and existing.content_hash == content_hash:
            return FileStats(path=relative_path, chunks=0, skipped=True)

        if existing is not None:
            await session.delete(existing)
            await session.flush()

        chunks = chunk_markdown(document.body, max_tokens=settings.chunk_max_tokens)
        record = Document(
            project=document.project,
            library=document.library,
            version=document.version,
            path=document.path,
            source_url=document.source_url,
            tier=document.tier,
            type=document.type,
            status=document.status or DocumentStatus.APPROVED.value,
            needs_review=document.needs_review,
            license=document.license,
            content_hash=content_hash,
            fetched_at=document.fetched_at,
            indexed_at=datetime.now(UTC),
        )
        session.add(record)
        await session.flush()

        if chunks:
            texts = [
                build_embedding_text(
                    library=document.library,
                    version=document.version,
                    heading_path=chunk.heading_path,
                    text=chunk.text,
                )
                for chunk in chunks
            ]
            vectors = await asyncio.to_thread(embedder.embed_documents, texts)
            session.add_all(
                [
                    Chunk(
                        document_id=record.id,
                        ord=chunk.ord,
                        heading_path=chunk.heading_path,
                        text=chunk.text,
                        token_count=chunk.token_count,
                        embedding=vector,
                        embedding_model=embedder.model_name,
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ]
            )

        await bump_index_version(session)
        await session.commit()
        return FileStats(path=relative_path, chunks=len(chunks), skipped=False)


async def bump_index_version(session: AsyncSession) -> int:
    """Increase the index version so cached searches stop matching."""
    state = await session.get(IndexState, 1)
    if state is None:
        state = IndexState(id=1, version=1)
        session.add(state)
    else:
        state.version += 1
    await session.flush()
    return state.version


async def _read(relative_path: str) -> KnowledgeDocument:
    try:
        return await asyncio.to_thread(read_document, relative_path)
    except (OSError, ValueError) as exc:
        logger.warning("cannot read %s: %s", relative_path, exc)
        raise IngestionError(f"{relative_path}: {exc}") from exc
