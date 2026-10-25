import pytest

from dev_docs_rag.services.chunking import chunk_markdown
from dev_docs_rag.services.rst import rst_to_markdown

pytestmark = pytest.mark.unit


def test_chunking_removes_nul_bytes():
    chunks = chunk_markdown("# Title\n\nin\x00_ function changed\n")

    assert chunks[0].text == "in_ function changed"


def test_rst_conversion_removes_nul_bytes():
    markdown = rst_to_markdown("Title\n=====\n\nin\x00_ function changed\n")

    assert "\x00" not in markdown
    assert "in_ function changed" in markdown


def test_mkdocs_anchor_is_removed_from_heading():
    chunks = chunk_markdown("## Lifespan Events { #lifespan-events }\n\nBody text.\n")

    assert chunks[0].heading_path == "Lifespan Events"
