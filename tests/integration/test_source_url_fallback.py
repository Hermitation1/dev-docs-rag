import pytest

from dev_docs_rag.services.frontmatter import parse_front_matter
from dev_docs_rag.services.knowledge import add_local_source

pytestmark = pytest.mark.integration


def test_source_url_falls_back_to_the_knowledge_path(knowledge_dir, tmp_path):
    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "guide.md").write_text("# Title\n\nBody.\n", encoding="utf-8")

    copied = add_local_source(
        library="fastapi",
        version="master",
        source=repo,
        docs_dir="docs",
        license_id="MIT",
        source_url=None,
    )

    meta, _ = parse_front_matter((knowledge_dir / copied[0]).read_text(encoding="utf-8"))
    assert meta["source_url"] == "fastapi/master/guide.md"
