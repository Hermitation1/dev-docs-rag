import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_search_fuses_vector_and_lexical_candidates(client: AsyncClient, seed_document):
    await seed_document(texts=("Use the lifespan handler for startup.",))
    await seed_document(
        library="pydantic",
        version="main",
        texts=("BaseModel validates fields.",),
        path="docs/models.md",
    )

    response = await client.get("/search", params={"q": "lifespan handler"})

    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert "notice" not in body
    assert "lifespan" in body["results"][0]["text"]
    assert body["results"][0]["source_url"].startswith("https://example.com/repo/blob/")


async def test_second_request_is_served_from_cache(client: AsyncClient, seed_document):
    await seed_document()

    first = await client.get("/search", params={"q": "lifespan"})
    second = await client.get("/search", params={"q": "lifespan"})

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert second.json()["results"] == first.json()["results"]


async def test_library_filter_excludes_other_libraries(client: AsyncClient, seed_document):
    await seed_document(library="fastapi", texts=("lifespan handler",))
    await seed_document(
        library="pydantic", version="main", texts=("lifespan field",), path="docs/p.md"
    )

    response = await client.get("/search", params={"q": "lifespan", "library": "pydantic"})

    assert {result["library"] for result in response.json()["results"]} == {"pydantic"}


async def test_status_filter_defaults_to_approved(client: AsyncClient, seed_document):
    await seed_document(path="docs/pending.md", texts=("pending lifespan",), status="pending")

    approved = await client.get("/search", params={"q": "lifespan"})
    pending = await client.get("/search", params={"q": "lifespan", "status": "pending"})

    assert approved.json()["results"] == []
    assert {result["status"] for result in pending.json()["results"]} == {"pending"}


async def test_top_k_above_the_limit_is_rejected(client: AsyncClient):
    response = await client.get("/search", params={"q": "lifespan", "top_k": 100})

    assert response.status_code == 422


async def test_empty_query_is_rejected(client: AsyncClient):
    response = await client.get("/search", params={"q": ""})

    assert response.status_code == 422
