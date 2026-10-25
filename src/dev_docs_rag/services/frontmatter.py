"""Front matter parsing and rendering for knowledge documents.

Every file in ``knowledge/`` starts with a YAML block that carries the metadata
search filters rely on: library, version, source_url and license are required.
Project documents additionally set ``project`` and usually ``tier: own``.
"""

import re
from collections.abc import Mapping
from typing import Any

import yaml

REQUIRED_FIELDS = ("library", "version", "source_url", "license")
DEFAULTS: dict[str, Any] = {
    "tier": "official",
    "type": "doc",
    "status": "approved",
}
ALLOWED = {
    "tier": {"own", "official", "web"},
    "type": {"doc", "best-practice", "note", "requirement", "adr"},
    "status": {"approved", "pending", "rejected"},
}
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_STRING_FIELDS = ("library", "version", "source_url", "license")


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split a document into its YAML metadata and the markdown body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            raw = "\n".join(lines[1:index])
            meta = yaml.safe_load(raw) or {}
            if not isinstance(meta, dict):
                raise ValueError("front matter must be a mapping")
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return dict(meta), body
    raise ValueError("front matter is not closed with '---'")


def render_front_matter(meta: Mapping[str, Any]) -> str:
    """Render metadata as a YAML block followed by a blank line."""
    payload = yaml.safe_dump(dict(meta), allow_unicode=True, sort_keys=False).strip()
    return f"---\n{payload}\n---\n\n"


def normalise(meta: Mapping[str, Any]) -> dict[str, Any]:
    """Fill defaults, reject wrong types and validate enumerated fields."""
    provided = {key: value for key, value in meta.items() if value is not None}

    missing = [field for field in REQUIRED_FIELDS if not provided.get(field)]
    if missing:
        raise ValueError(f"front matter is missing required fields: {', '.join(missing)}")

    for field in _STRING_FIELDS:
        if not isinstance(provided[field], str):
            raise ValueError(
                f"{field} must be a quoted string, got {type(provided[field]).__name__}"
            )

    result = {**DEFAULTS, **provided}
    for field, allowed in ALLOWED.items():
        value = str(result[field]).strip()
        if value not in allowed:
            raise ValueError(f"{field} must be one of {sorted(allowed)}, got {value!r}")
        result[field] = value

    for field in _STRING_FIELDS:
        result[field] = str(result[field]).strip()

    project = provided.get("project")
    if project is not None:
        if not isinstance(project, str):
            raise ValueError("project must be a quoted string")
        project = project.strip()
        if not SLUG_PATTERN.match(project):
            raise ValueError(f"project must match a slug, got {project!r}")
        result["project"] = project
    return result
