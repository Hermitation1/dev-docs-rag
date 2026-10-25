"""Hybrid search: vector and full-text candidates fused with reciprocal rank fusion."""

import asyncio
import logging
from dataclasses import asdict, dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import Chunk, Document, DocumentStatus, IndexState
from .cache import RedisCache, embedding_cache_key, search_cache_key
from .embeddings import Embedder

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchHit:
    """One chunk returned to the caller."""

    chunk_id: int
    project: str | None
    library: str
    version: str
    tier: str
    type: str
    status: str
    path: str
    heading_path: str
    source_url: str
    score: float
    text: str


def fuse_rrf(vector_ids: list[int], lexical_ids: list[int], k: int) -> list[tuple[int, float]]:
    """Fuse two ranked lists: score = sum of 1 / (k + rank)."""
    scores: dict[int, float] = {}
    for ranked in (vector_ids, lexical_ids):
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


async def search_chunks(
    query: str,
    *,
    session: AsyncSession,
    embedder: Embedder,
    settings: Settings,
    project: str | None = None,
    library: str | None = None,
    version: str | None = None,
    status: str = DocumentStatus.APPROVED.value,
    top_k: int | None = None,
    vector: list[float] | None = None,
) -> list[SearchHit]:
    """Return the best chunks by fusing vector and lexical candidates."""
    limit = top_k or settings.search_top_k
    filters = [Document.status == status]
    if project is None:
        filters.append(Document.project.is_(None))
    else:
        filters.append(or_(Document.project == project, Document.project.is_(None)))
    if library is not None:
        filters.append(Document.library == library)
    if version is not None:
        filters.append(Document.version == version)

    if vector is None:
        vector = await asyncio.to_thread(embedder.embed_query, query)
    distance = Chunk.embedding.cosine_distance(vector)
    vector_stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(*filters)
        .order_by(distance)
        .limit(settings.search_candidates)
    )

    tsquery = func.plainto_tsquery("simple", query)
    lexical_stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.tsv.op("@@")(tsquery), *filters)
        .order_by(func.ts_rank_cd(Chunk.tsv, tsquery).desc())
        .limit(settings.search_candidates)
    )

    vector_rows = (await session.execute(vector_stmt)).all()
    lexical_rows = (await session.execute(lexical_stmt)).all()

    by_id = {chunk.id: (chunk, document) for chunk, document in [*vector_rows, *lexical_rows]}
    fused = fuse_rrf(
        [chunk.id for chunk, _ in vector_rows],
        [chunk.id for chunk, _ in lexical_rows],
        settings.rrf_k,
    )

    hits: list[SearchHit] = []
    for chunk_id, score in fused[:limit]:
        chunk, document = by_id[chunk_id]
        hits.append(
            SearchHit(
                chunk_id=chunk.id,
                project=document.project,
                library=document.library,
                version=document.version,
                tier=document.tier,
                type=document.type,
                status=document.status,
                path=document.path,
                heading_path=chunk.heading_path,
                source_url=document.source_url,
                score=score,
                text=chunk.text,
            )
        )
    return hits


async def search_with_cache(
    query: str,
    *,
    session: AsyncSession,
    embedder: Embedder,
    cache: RedisCache,
    settings: Settings,
    project: str | None = None,
    library: str | None = None,
    version: str | None = None,
    status: str = DocumentStatus.APPROVED.value,
    top_k: int | None = None,
) -> tuple[list[SearchHit], bool]:
    """Return search hits and whether they came from the cache."""
    limit = top_k or settings.search_top_k
    index_version = (
        await session.scalar(select(IndexState.version).where(IndexState.id == 1))
    ) or 0

    key = search_cache_key(
        model=embedder.model_name,
        index_version=index_version,
        project=project,
        library=library,
        version=version,
        status=status,
        top_k=limit,
        query=query,
    )
    cached = await cache.get_json(key)
    if cached is not None:
        try:
            return [SearchHit(**item) for item in cached], True
        except (TypeError, ValueError) as exc:
            logger.warning("ignoring cache entry written by an older format: %s", exc)

    embed_key = embedding_cache_key(model=embedder.model_name, query=query)
    vector = await cache.get_vector(embed_key)
    if vector is None:
        vector = await asyncio.to_thread(embedder.embed_query, query)
        await cache.set_vector(embed_key, vector)

    hits = await search_chunks(
        query,
        session=session,
        embedder=embedder,
        settings=settings,
        project=project,
        library=library,
        version=version,
        status=status,
        top_k=limit,
        vector=vector,
    )
    await cache.set_json(key, [asdict(hit) for hit in hits])
    return hits, False
