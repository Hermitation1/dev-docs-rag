import subprocess

import pytest

from dev_docs_rag.services.fetch import fetch_git_source
from dev_docs_rag.services.frontmatter import parse_front_matter

pytestmark = pytest.mark.integration


def _git(cwd, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _create_repo(root):
    repo = root / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "guide.md").write_text("# Title\n\nBody.\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "docs")
    return repo


def test_fetch_copies_docs_and_sets_license(knowledge_dir, tmp_path):
    repo = _create_repo(tmp_path)

    copied = fetch_git_source(
        library="fastapi",
        version="main",
        git_url=str(repo),
        ref="main",
        docs_dir="docs",
        license_id="MIT",
    )

    assert copied == ["fastapi/main/guide.md"]
    meta, body = parse_front_matter((knowledge_dir / copied[0]).read_text(encoding="utf-8"))
    assert meta["license"] == "MIT"
    assert body.strip() == "# Title\n\nBody."


def test_fetch_reports_a_missing_repository(knowledge_dir, tmp_path):
    with pytest.raises(ValueError, match="git clone failed"):
        fetch_git_source(library="x", version="1", git_url=str(tmp_path / "missing"), ref="main")
