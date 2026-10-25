import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _write_docs(root):
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "guide.md").write_text("# Startup\n\nUse the lifespan handler.\n", encoding="utf-8")
    return docs


async def test_create_source_copies_files_and_queues(
    client: AsyncClient, enqueued, tmp_path, knowledge_dir
):
    docs = _write_docs(tmp_path / "repo")

    response = await client.post(
        "/sources",
        json={
            "library": "fastapi",
            "version": "0.115",
            "path": str(docs.parent),
            "docs_dir": "docs",
            "license": "MIT",
        },
    )

    assert response.status_code == 202
    assert response.json() == {"queued": 1}
    assert len(enqueued) == 1
    copied = knowledge_dir / "fastapi" / "0.115" / "guide.md"
    assert copied.exists()
    assert "library: fastapi" in copied.read_text(encoding="utf-8")


async def test_missing_path_is_rejected(client: AsyncClient, enqueued, tmp_path):
    response = await client.post(
        "/sources",
        json={"library": "fastapi", "version": "0.115", "path": str(tmp_path / "missing")},
    )

    assert response.status_code == 422
    assert enqueued == []


async def test_directory_without_markdown_is_rejected(client: AsyncClient, enqueued, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()

    response = await client.post(
        "/sources",
        json={"library": "fastapi", "version": "0.115", "path": str(empty)},
    )

    assert response.status_code == 422
    assert enqueued == []
