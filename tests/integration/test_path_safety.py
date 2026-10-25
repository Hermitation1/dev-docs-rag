import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _docs(root):
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "guide.md").write_text("# Title\n\nBody.\n", encoding="utf-8")
    return docs


async def test_library_cannot_escape_the_knowledge_dir(
    client: AsyncClient, enqueued, tmp_path, knowledge_dir
):
    docs = _docs(tmp_path / "repo")

    response = await client.post(
        "/sources",
        json={"library": "../../escape", "version": "1", "path": str(docs)},
    )

    assert response.status_code == 422
    assert enqueued == []
    assert not (knowledge_dir.parent / "escape").exists()


async def test_version_cannot_contain_path_separators(client: AsyncClient, enqueued, tmp_path):
    docs = _docs(tmp_path / "repo")

    response = await client.post(
        "/sources",
        json={"library": "fastapi", "version": "../1", "path": str(docs)},
    )

    assert response.status_code == 422
    assert enqueued == []
