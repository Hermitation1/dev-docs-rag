import pytest

from dev_docs_rag.services.chunking import build_embedding_text, chunk_markdown, estimate_tokens

pytestmark = pytest.mark.unit


def test_splits_sections_and_builds_heading_path():
    markdown = "# Install\n\nInstall it.\n\n## Extras\n\nOptional parts.\n"

    chunks = chunk_markdown(markdown)

    assert [chunk.heading_path for chunk in chunks] == ["Install", "Install > Extras"]
    assert [chunk.text for chunk in chunks] == ["Install it.", "Optional parts."]
    assert [chunk.ord for chunk in chunks] == [0, 1]


def test_heading_inside_code_fence_is_not_a_heading():
    markdown = "# A\n\n```python\n# not a heading\ndef f():\n    pass\n```\n"

    chunks = chunk_markdown(markdown, max_tokens=10)

    assert len(chunks) == 1
    assert "# not a heading" in chunks[0].text
    assert chunks[0].text.count("```") == 2
    assert chunks[0].heading_path == "A"


def test_long_section_is_split_into_bounded_chunks():
    paragraph = "word " * 200
    markdown = f"# Big\n\n{paragraph}\n\n{paragraph}\n"

    chunks = chunk_markdown(markdown, max_tokens=100)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 110 for chunk in chunks)
    assert all(chunk.heading_path == "Big" for chunk in chunks)
    assert [chunk.ord for chunk in chunks] == list(range(len(chunks)))


def test_heading_levels_reset_the_path():
    markdown = "# A\n\nText a.\n\n## B\n\nText b.\n\n# C\n\nText c.\n"

    chunks = chunk_markdown(markdown)

    assert [chunk.heading_path for chunk in chunks] == ["A", "A > B", "C"]


def test_content_before_first_heading_has_empty_path():
    markdown = "Intro line.\n\n# Title\n\nBody.\n"

    chunks = chunk_markdown(markdown)

    assert chunks[0].heading_path == ""
    assert chunks[0].text == "Intro line."


def test_empty_document_produces_no_chunks():
    assert chunk_markdown("\n\n") == []


def test_embedding_text_carries_the_origin():
    text = build_embedding_text(
        library="fastapi", version="0.115", heading_path="Tutorial > First steps", text="Body."
    )

    assert text.startswith("fastapi v0.115 > Tutorial > First steps")
    assert text.endswith("Body.")


def test_token_estimate_is_never_zero():
    assert estimate_tokens("") == 1
    assert estimate_tokens("12345678") == 2
