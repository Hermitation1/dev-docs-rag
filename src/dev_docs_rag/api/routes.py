"""HTTP routes for ingestion and search."""

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import DocumentStatus
from ..services.cache import RedisCache
from ..services.embeddings import Embedder
from ..services.knowledge import add_local_source
from ..services.search import search_with_cache
from ..worker.tasks import index_file
from .deps import get_cache, get_embedder, get_session
from .schemas import SearchResponse, SearchResult, SourceCreate, SourceQueued

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CacheDep = Annotated[RedisCache, Depends(get_cache)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder)]


@router.post("/sources", response_model=SourceQueued, status_code=202)
async def create_source(payload: SourceCreate) -> SourceQueued:
    """Copy a local documentation directory into ``knowledge/`` and queue every file."""
    try:
        copied = await asyncio.to_thread(
            add_local_source,
            library=payload.library,
            version=payload.version,
            project=payload.project,
            source=Path(payload.path),
            docs_dir=payload.docs_dir,
            license_id=payload.license,
            source_url=payload.source_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        for relative in copied:
            index_file.delay(relative)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="task queue is unavailable") from exc
    return SourceQueued(queued=len(copied))


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=500)],
    session: SessionDep,
    cache: CacheDep,
    embedder: EmbedderDep,
    project: Annotated[str | None, Query(max_length=64)] = None,
    library: Annotated[str | None, Query(max_length=64)] = None,
    version: Annotated[str | None, Query(max_length=64)] = None,
    status: Annotated[DocumentStatus, Query()] = DocumentStatus.APPROVED,
    top_k: Annotated[int | None, Query(ge=1)] = None,
) -> SearchResponse:
    """Return the best documentation chunks for a query."""
    settings = get_settings()
    limit = top_k or settings.search_top_k
    if limit > settings.search_max_top_k:
        raise HTTPException(
            status_code=422,
            detail=f"top_k must be between 1 and {settings.search_max_top_k}",
        )

    hits, cached = await search_with_cache(
        q,
        session=session,
        embedder=embedder,
        cache=cache,
        settings=settings,
        project=project,
        library=library,
        version=version,
        status=status.value,
        top_k=limit,
    )
    return SearchResponse(
        cached=cached,
        results=[SearchResult(**asdict(hit)) for hit in hits],
    )
