import pytest
from pydantic import ValidationError

from dev_docs_rag.config import Settings

pytestmark = pytest.mark.unit


def test_candidates_below_top_k_are_rejected():
    with pytest.raises(ValidationError, match="SEARCH_CANDIDATES"):
        Settings(search_top_k=10, search_candidates=5)


def test_top_k_above_max_is_rejected():
    with pytest.raises(ValidationError, match="SEARCH_TOP_K"):
        Settings(search_top_k=30, search_max_top_k=20)


def test_defaults_are_consistent():
    settings = Settings()

    assert settings.search_candidates >= settings.search_top_k
    assert settings.search_top_k <= settings.search_max_top_k
