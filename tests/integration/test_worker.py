import pytest
from sqlalchemy import func, select

from dev_docs_rag.db import get_session_factory
from dev_docs_rag.models import Chunk, Document, IndexState
from dev_docs_rag.services.embeddings import FakeEmbedder
from dev_docs_rag.worker import tasks

pytestmark = pytest.mark.integration

FRONT_MATTER = (
    "---\n"
    "library: fastapi\n"
    "version: master\n"
    "source_url: https://example.com/repo\n"
    "license: MIT\n"
    "---\n\n"
)


def _write_document(knowledge_root, body: str = "# Startup\n\nUse the lifespan handler.\n"):
    path = knowledge_root / "fastapi" / "master" / "guide.md"
    path.parent.mkdir(parents=True)
    path.write_text(FRONT_MATTER + body, encoding="utf-8")
    return "fastapi/master/guide.md"


async def _count_chunks() -> int:
    async with get_session_factory()() as session:
        return await session.scalar(select(func.count(Chunk.id))) or 0


async def _index_version() -> int:
    async with get_session_factory()() as session:
        return await session.scalar(select(IndexState.version).where(IndexState.id == 1)) or 0


async def test_worker_indexes_a_knowledge_file(knowledge_dir, monkeypatch):
    relative = _write_document(knowledge_dir)
    monkeypatch.setattr(tasks, "_embedder", FakeEmbedder())

    stats = await tasks._index(relative)

    assert stats.chunks == 1
    assert stats.skipped is False
    assert await _count_chunks() == 1
    async with get_session_factory()() as session:
        document = await session.scalar(select(Document))
        assert document is not None
        assert document.library == "fastapi"
        assert document.license == "MIT"
        assert document.indexed_at is not None


async def test_second_run_skips_unchanged_documents(knowledge_dir, monkeypatch):
    relative = _write_document(knowledge_dir)
    monkeypatch.setattr(tasks, "_embedder", FakeEmbedder())

    await tasks._index(relative)
    stats = await tasks._index(relative)

    assert stats.skipped is True
    assert await _count_chunks() == 1


async def test_reindex_replaces_chunks_and_bumps_the_version(knowledge_dir, monkeypatch):
    relative = _write_document(knowledge_dir)
    monkeypatch.setattr(tasks, "_embedder", FakeEmbedder())
    await tasks._index(relative)
    before = await _index_version()

    path = knowledge_dir / relative
    path.write_text(FRONT_MATTER + "# Startup\n\nUse lifespan and shutdown.\n", encoding="utf-8")
    stats = await tasks._index(relative)

    assert stats.skipped is False
    assert await _count_chunks() == 1
    assert await _index_version() == before + 1


async def test_document_without_front_matter_is_rejected(knowledge_dir, monkeypatch):
    path = knowledge_dir / "broken.md"
    path.write_text("# No metadata\n", encoding="utf-8")
    monkeypatch.setattr(tasks, "_embedder", FakeEmbedder())

    with pytest.raises(Exception, match="front matter"):
        await tasks._index("broken.md")
