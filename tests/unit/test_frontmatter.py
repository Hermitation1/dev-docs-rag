import pytest

from dev_docs_rag.services.frontmatter import normalise, parse_front_matter, render_front_matter

pytestmark = pytest.mark.unit


def test_parses_metadata_and_body():
    text = "---\nlibrary: fastapi\nversion: '0.115'\n---\n\n# Title\n\nBody.\n"

    meta, body = parse_front_matter(text)

    assert meta == {"library": "fastapi", "version": "0.115"}
    assert body.startswith("# Title")


def test_renders_a_round_trip():
    meta = {
        "library": "fastapi",
        "version": "master",
        "source_url": "https://example.com",
        "license": "MIT",
    }

    text = render_front_matter(meta)
    parsed, body = parse_front_matter(text + "Body.")

    assert parsed["library"] == "fastapi"
    assert body == "Body."


def test_missing_required_field_is_reported():
    with pytest.raises(ValueError, match="license"):
        normalise({"library": "fastapi", "version": "1", "source_url": "https://example.com"})


def test_defaults_are_applied():
    clean = normalise(
        {
            "library": "fastapi",
            "version": "1",
            "source_url": "https://example.com",
            "license": "MIT",
        }
    )

    assert clean["tier"] == "official"
    assert clean["type"] == "doc"
    assert clean["status"] == "approved"


def test_unclosed_front_matter_is_reported():
    with pytest.raises(ValueError, match="closed"):
        parse_front_matter("---\nlibrary: fastapi\n")
