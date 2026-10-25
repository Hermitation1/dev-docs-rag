import pytest

from dev_docs_rag.services.frontmatter import normalise

pytestmark = pytest.mark.unit

BASE = {
    "library": "fastapi",
    "version": "0.115",
    "source_url": "https://example.com/repo",
    "license": "MIT",
}


def test_project_is_kept():
    clean = normalise({**BASE, "project": "myapp"})

    assert clean["project"] == "myapp"


def test_project_slug_is_validated():
    with pytest.raises(ValueError, match="project must match a slug"):
        normalise({**BASE, "project": "../escape"})


def test_project_documents_accept_new_types():
    clean = normalise({**BASE, "project": "myapp", "type": "requirement"})

    assert clean["type"] == "requirement"
