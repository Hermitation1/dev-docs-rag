import pytest
from sqlalchemy import select

from dev_docs_rag.db import get_session_factory
from dev_docs_rag.models import Document
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
    "# Startup\n\nUse the lifespan handler.\n"
)


def _write_document(root, text: str = FRONT_MATTER) -> str:
    path = root / "fastapi" / "master" / "guide.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return "fastapi/master/guide.md"


async def test_model_change_forces_reindex(knowledge_dir, monkeypatch):
    relative = _write_document(knowledge_dir)
    monkeypatch.setattr(tasks, "_embedder", FakeEmbedder(model_name="fake-a"))
    assert (await tasks._index(relative)).skipped is False

    monkeypatch.setattr(tasks, "_embedder", FakeEmbedder(model_name="fake-b"))
    assert (await tasks._index(relative)).skipped is False


async def test_metadata_change_forces_reindex(knowledge_dir, monkeypatch):
    relative = _write_document(knowledge_dir)
    monkeypatch.setattr(tasks, "_embedder", FakeEmbedder())
    await tasks._index(relative)

    _write_document(knowledge_dir, FRONT_MATTER.replace("license: MIT", "license: Apache-2.0"))
    stats = await tasks._index(relative)

    assert stats.skipped is False
    async with get_session_factory()() as session:
        document = await session.scalar(select(Document))
        assert document is not None
        assert document.license == "Apache-2.0"
