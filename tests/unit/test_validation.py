import pytest

from dev_docs_rag.services.frontmatter import normalise

pytestmark = pytest.mark.unit

BASE = {
    "library": "fastapi",
    "version": "0.115",
    "source_url": "https://example.com/repo",
    "license": "MIT",
}


def test_rejects_unknown_status():
    with pytest.raises(ValueError, match="status must be one of"):
        normalise({**BASE, "status": "aproved"})


def test_rejects_non_string_library():
    with pytest.raises(ValueError, match="library must be a quoted string"):
        normalise({**BASE, "library": True})


def test_explicit_null_does_not_override_defaults():
    clean = normalise({**BASE, "tier": None, "status": None})

    assert clean["tier"] == "official"
    assert clean["status"] == "approved"


def test_strips_surrounding_spaces():
    clean = normalise({**BASE, "license": "  MIT  ", "source_url": " https://example.com "})

    assert clean["license"] == "MIT"
    assert clean["source_url"] == "https://example.com"
