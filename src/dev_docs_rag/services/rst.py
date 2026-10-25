"""Convert reStructuredText to Markdown using docutils.

The converter targets documentation sources, not arbitrary rST: Sphinx-only
directives are either aliased to docutils equivalents or dropped, and unknown
interpreted roles degrade to their plain text instead of failing the ingest.
"""

import io
import re

from docutils import nodes
from docutils.core import publish_doctree
from docutils.parsers.rst import directives
from docutils.parsers.rst.directives.body import CodeBlock

_DROPPED_DIRECTIVE = re.compile(
    r"^[ \t]*\.\.[ \t]+"
    r"(?:currentmodule|module|automodule|autoclass|autofunction|autodata|"
    r"autoexception|index|meta|toctree|highlight)::.*$",
    re.MULTILINE,
)
_ADMONITION_DIRECTIVE = re.compile(
    r"^([ \t]*)\.\.[ \t]+(?:versionadded|versionchanged|deprecated|versionremoved)::[ \t]*(.*)$",
    re.MULTILINE,
)
_ROLE = re.compile(r":\w+:`([^`]+)`")


def _rewrite_admonition(match: re.Match[str]) -> str:
    indent, rest = match.group(1), match.group(2).strip()
    if not rest:
        return f"{indent}.. note::"
    return f"{indent}.. note::\n\n{indent}   {rest}"


def _strip_roles(text: str) -> str:
    """Replace Sphinx roles with their visible text: ``:class:`Foo``` becomes ``Foo``."""

    def replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        if " <" in inner and inner.endswith(">"):
            inner = inner.split(" <", 1)[0]
        return inner.lstrip("~")

    return _ROLE.sub(replace, text)


def rst_to_markdown(text: str) -> str:
    """Render reStructuredText as Markdown, keeping headings, code blocks and lists."""
    directives.register_directive("code-block", CodeBlock)
    directives.register_directive("sourcecode", CodeBlock)

    source = _ADMONITION_DIRECTIVE.sub(_rewrite_admonition, _DROPPED_DIRECTIVE.sub("", text))
    doctree = publish_doctree(
        source,
        settings_overrides={
            "report_level": 5,
            "halt_level": 5,
            "warning_stream": io.StringIO(),
            "doctitle_xform": False,
        },
    )
    blocks = [_render_node(child, depth=0) for child in doctree.children]
    markdown = "\n\n".join(block for block in blocks if block.strip()).strip()
    return markdown.replace("\x00", "")


def _render_node(node: nodes.Node, depth: int) -> str:
    if isinstance(node, nodes.section):
        title = next((child for child in node.children if isinstance(child, nodes.title)), None)
        heading = f"{'#' * min(depth + 1, 6)} {_inline(title)}" if title is not None else ""
        body = [
            _render_node(child, depth + 1)
            for child in node.children
            if not isinstance(child, nodes.title)
        ]
        return "\n\n".join(part for part in [heading, *body] if part.strip())

    if isinstance(node, nodes.title):
        return f"{'#' * min(depth + 1, 6)} {_inline(node)}"

    if isinstance(node, nodes.paragraph):
        return _inline(node)

    if isinstance(node, nodes.literal_block):
        classes = [name for name in node.get("classes", []) if name != "code"]
        language = node.get("language") or (classes[0] if classes else "")
        return f"```{language}\n{node.astext()}\n```"

    if isinstance(node, nodes.bullet_list):
        return "\n".join(f"- {_render_node(item, depth).strip()}" for item in node.children)

    if isinstance(node, nodes.enumerated_list):
        start = node.get("start", 1)
        return "\n".join(
            f"{number}. {_render_node(item, depth).strip()}"
            for number, item in enumerate(node.children, start=start)
        )

    if isinstance(node, nodes.list_item):
        return "\n".join(
            part for part in (_render_node(child, depth) for child in node.children) if part.strip()
        )

    if isinstance(node, nodes.definition_list):
        lines = []
        for item in node.children:
            term = next((child for child in item.children if isinstance(child, nodes.term)), None)
            definition = next(
                (child for child in item.children if isinstance(child, nodes.definition)), None
            )
            label = f"**{_inline(term)}**" if term is not None else ""
            body = _render_node(definition, depth) if definition is not None else ""
            lines.append(f"{label} — {body}".strip(" —"))
        return "\n".join(lines)

    if isinstance(node, nodes.Admonition):
        body = "\n\n".join(
            part for part in (_render_node(child, depth) for child in node.children) if part.strip()
        )
        return "\n".join(f"> {line}" for line in body.splitlines())

    if isinstance(node, nodes.block_quote):
        body = "\n\n".join(
            part for part in (_render_node(child, depth) for child in node.children) if part.strip()
        )
        return "\n".join(f"> {line}" for line in body.splitlines())

    if isinstance(node, nodes.transition):
        return "---"

    if isinstance(node, (nodes.system_message, nodes.target, nodes.comment)):
        return ""

    return _strip_roles(node.astext())


def _inline(node: nodes.Node) -> str:
    """Render the inline content of a node as plain Markdown text."""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, nodes.Text):
            parts.append(_strip_roles(str(child)))
        elif isinstance(child, nodes.literal):
            parts.append(f"`{child.astext()}`")
        elif isinstance(child, nodes.strong):
            parts.append(f"**{child.astext()}**")
        elif isinstance(child, nodes.emphasis):
            parts.append(f"*{child.astext()}*")
        elif isinstance(child, nodes.reference):
            target = child.get("refuri")
            parts.append(f"[{child.astext()}]({target})" if target else child.astext())
        else:
            parts.append(child.astext())
    return "".join(parts)
