import pytest
from celery import states

from dev_docs_rag.services.embeddings import FakeEmbedder
from dev_docs_rag.worker import tasks

pytestmark = pytest.mark.integration


def test_invalid_front_matter_is_dead_lettered(knowledge_dir, monkeypatch):
    path = knowledge_dir / "broken.md"
    path.write_text("# Missing required metadata\n", encoding="utf-8")
    monkeypatch.setattr(tasks, "_embedder", FakeEmbedder())

    result = tasks.index_file.apply(args=["broken.md"])

    assert result.state == states.REJECTED
