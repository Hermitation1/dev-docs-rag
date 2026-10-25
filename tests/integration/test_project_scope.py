import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _docs(root):
    docs = root / "docs"
    docs.mkdir(parents=True)
    (docs / "rules.md").write_text("# Rule\n\nNever use session.query.\n", encoding="utf-8")
    return docs


async def test_project_ingest_lands_in_projects_dir(
    client: AsyncClient, enqueued, tmp_path, knowledge_dir
):
    docs = _docs(tmp_path / "repo")

    response = await client.post(
        "/sources",
        json={
            "library": "notes",
            "version": "current",
            "project": "myapp",
            "path": str(docs),
            "license": "proprietary",
        },
    )

    assert response.status_code == 202
    copied = knowledge_dir / "_projects" / "myapp" / "rules.md"
    assert copied.exists()
    text = copied.read_text(encoding="utf-8")
    assert "project: myapp" in text
    assert "tier: own" in text
    assert enqueued == ["_projects/myapp/rules.md"]


async def test_search_without_project_hides_project_documents(client: AsyncClient, seed_document):
    await seed_document(
        texts=("project rule about lifespan",),
        project="myapp",
        path="_projects/myapp/rule.md",
    )
    await seed_document(texts=("library docs about lifespan",))

    without = await client.get("/search", params={"q": "lifespan"})
    with_project = await client.get("/search", params={"q": "lifespan", "project": "myapp"})

    assert without.status_code == 200
    assert all(hit["project"] is None for hit in without.json()["results"])
    assert {hit["project"] for hit in with_project.json()["results"]} == {"myapp", None}


async def test_project_filter_participates_in_the_cache_key(client: AsyncClient, seed_document):
    await seed_document(texts=("project lifespan",), project="myapp", path="_projects/a.md")
    await seed_document(texts=("project lifespan",), project="other", path="_projects/b.md")

    first = await client.get("/search", params={"q": "lifespan", "project": "myapp"})
    second = await client.get("/search", params={"q": "lifespan", "project": "other"})

    assert first.json()["cached"] is False
    assert second.json()["cached"] is False
    assert {hit["project"] for hit in first.json()["results"]} == {"myapp"}
    assert {hit["project"] for hit in second.json()["results"]} == {"other"}
