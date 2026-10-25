import pytest

from dev_docs_rag.services.cache import search_cache_key

pytestmark = pytest.mark.unit


def _key(**overrides):
    payload = {
        "model": "m",
        "index_version": 1,
        "project": None,
        "library": "fastapi",
        "version": "0.115",
        "status": "approved",
        "top_k": 5,
        "query": "lifespan",
    }
    payload.update(overrides)
    return search_cache_key(**payload)


def test_index_version_invalidates_cached_results():
    assert _key(index_version=1) != _key(index_version=2)


def test_different_models_do_not_share_a_key():
    assert _key(model="a") != _key(model="b")


def test_query_normalisation_avoids_duplicate_entries():
    assert _key(query="  Lifespan  ") == _key(query="lifespan")


def test_filters_and_top_k_take_part_in_the_key():
    assert _key(library="pydantic") != _key()
    assert _key(status="pending") != _key()
    assert _key(top_k=10) != _key()
