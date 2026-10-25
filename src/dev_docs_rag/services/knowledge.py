"""The ``knowledge/`` directory: the git-tracked source of truth for documents."""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..config import get_settings
from .frontmatter import normalise, parse_front_matter, render_front_matter

MARKDOWN_SUFFIX = ".md"
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
PROJECTS_DIR = "_projects"


@dataclass(frozen=True)
class KnowledgeDocument:
    """A parsed document from the knowledge directory."""

    path: str
    project: str | None
    library: str
    version: str
    source_url: str
    license: str
    tier: str
    type: str
    status: str
    fetched_at: date | None
    needs_review: bool
    body: str


def _validate_slug(value: str, field: str) -> None:
    if not SLUG_PATTERN.match(value):
        raise ValueError(
            f"{field} must match {SLUG_PATTERN.pattern!r} (lowercase letters, digits, . _ -): "
            f"{value!r}"
        )


def resolve_document(relative_path: str) -> Path:
    """Resolve a knowledge-relative path, refusing to escape the directory."""
    root = get_settings().knowledge_dir.resolve()
    path = (root / relative_path).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"path escapes the knowledge directory: {relative_path}")
    return path


def read_document(relative_path: str) -> KnowledgeDocument:
    """Read and parse one document from the knowledge directory."""
    path = resolve_document(relative_path)
    meta, body = parse_front_matter(path.read_text(encoding="utf-8", errors="replace"))
    try:
        clean = normalise(meta)
    except ValueError as exc:
        raise ValueError(f"{relative_path}: {exc}") from exc
    return KnowledgeDocument(
        path=relative_path,
        project=clean.get("project"),
        library=clean["library"],
        version=clean["version"],
        source_url=str(clean["source_url"]),
        license=str(clean["license"]),
        tier=clean["tier"],
        type=clean["type"],
        status=clean["status"],
        fetched_at=_as_date(clean.get("fetched_at")),
        needs_review=bool(clean.get("needs_review", False)),
        body=body,
    )


def iter_documents() -> list[str]:
    """List every markdown document under the knowledge directory."""
    root = get_settings().knowledge_dir
    if not root.is_dir():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob(f"*{MARKDOWN_SUFFIX}"))


def add_local_source(
    *,
    library: str,
    version: str,
    source: Path,
    docs_dir: str | None,
    license_id: str,
    source_url: str | None,
    project: str | None = None,
) -> list[str]:
    """Copy markdown into ``knowledge/``: library docs by version, project docs by project."""
    _validate_slug(library, "library")
    _validate_slug(version, "version")
    if project is not None:
        _validate_slug(project, "project")

    base = source / docs_dir if docs_dir else source
    if not base.is_dir():
        raise ValueError(f"source directory not found: {base}")

    root = get_settings().knowledge_dir
    if project is not None:
        target_root = (root / PROJECTS_DIR / project).resolve()
    else:
        target_root = (root / library / version).resolve()
    root_resolved = root.resolve()
    if root_resolved not in target_root.parents:
        raise ValueError(f"target directory escapes the knowledge dir: {target_root}")
    copied: list[str] = []

    for path in sorted(base.rglob(f"*{MARKDOWN_SUFFIX}")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8", errors="replace"))
        try:
            repo_relative = path.relative_to(source).as_posix()
        except ValueError:
            repo_relative = path.relative_to(base).as_posix()
        destination = target_root / path.relative_to(base)
        if source_url:
            file_url = f"{source_url.rstrip('/')}/{repo_relative}"
        elif meta.get("source_url"):
            file_url = str(meta["source_url"])
        else:
            file_url = destination.relative_to(root_resolved).as_posix()
        metadata = {
            "library": library,
            "version": version,
            "source_url": file_url,
            "license": license_id or meta.get("license") or "unknown",
            "tier": "own" if project is not None else meta.get("tier", "official"),
            "type": meta.get("type", "doc"),
            "status": meta.get("status", "approved"),
            "fetched_at": meta.get("fetched_at") or date.today().isoformat(),
        }
        if project is not None:
            metadata["project"] = project
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_front_matter(metadata) + body, encoding="utf-8")
        copied.append(destination.relative_to(root_resolved).as_posix())

    if not copied:
        raise ValueError(f"no markdown files found under {base}")
    return copied


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
