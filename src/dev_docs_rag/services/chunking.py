"""Heading-aware Markdown chunking that never splits fenced code blocks."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_ANCHOR_RE = re.compile(r"\s*\{\s*#[^}]*\}\s*$")

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from character length (about four characters per token)."""
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass(frozen=True)
class Chunk:
    """A retrievable piece of a document."""

    ord: int
    heading_path: str
    text: str
    token_count: int


@dataclass(frozen=True)
class _Section:
    path: tuple[str, ...]
    lines: tuple[str, ...]


def build_embedding_text(*, library: str, version: str, heading_path: str, text: str) -> str:
    """Prefix a chunk with its origin so short fragments keep their context."""
    header = f"{library} v{version}"
    if heading_path:
        header = f"{header} > {heading_path}"
    return f"{header}\n\n{text}"


def chunk_markdown(markdown: str, *, max_tokens: int = 600) -> list[Chunk]:
    """Split Markdown into chunks along h1-h3 headings, keeping code blocks whole."""
    markdown = markdown.replace("\x00", "")
    chunks: list[Chunk] = []
    for section in _split_sections(markdown):
        blocks: list[str] = []
        for block in _split_blocks(section.lines):
            if _is_code_block(block):
                blocks.append(block)
            else:
                blocks.extend(_split_long_block(block, max_tokens))
        for text in _pack(blocks, max_tokens):
            chunks.append(
                Chunk(
                    ord=len(chunks),
                    heading_path=" > ".join(section.path),
                    text=text,
                    token_count=estimate_tokens(text),
                )
            )
    return chunks


def _split_sections(markdown: str) -> list[_Section]:
    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []
    current_path: tuple[str, ...] = ()
    buffer: list[str] = []
    in_code = False

    for line in markdown.splitlines():
        if _FENCE_RE.match(line):
            in_code = not in_code
            buffer.append(line)
            continue
        match = None if in_code else _HEADING_RE.match(line)
        if match is None:
            buffer.append(line)
            continue
        if any(item.strip() for item in buffer):
            sections.append(_Section(path=current_path, lines=tuple(buffer)))
        level = len(match.group(1))
        stack = [entry for entry in stack if entry[0] < level]
        title = _ANCHOR_RE.sub("", match.group(2)).strip()
        stack.append((level, title))
        current_path = tuple(title for _, title in stack)
        buffer = []

    if any(item.strip() for item in buffer):
        sections.append(_Section(path=current_path, lines=tuple(buffer)))
    return sections


def _split_blocks(lines: Sequence[str]) -> list[str]:
    blocks: list[str] = []
    buffer: list[str] = []
    in_code = False

    for line in lines:
        if _FENCE_RE.match(line):
            in_code = not in_code
            buffer.append(line)
            continue
        if not in_code and not line.strip():
            if buffer:
                blocks.append("\n".join(buffer).strip())
                buffer = []
            continue
        buffer.append(line)

    if buffer:
        blocks.append("\n".join(buffer).strip())
    return [block for block in blocks if block]


def _is_code_block(block: str) -> bool:
    return bool(_FENCE_RE.match(block.lstrip("\n")))


def _split_long_block(block: str, max_tokens: int) -> list[str]:
    if estimate_tokens(block) <= max_tokens:
        return [block]

    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_RE.split(block):
        if estimate_tokens(sentence) > max_tokens:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_split_by_words(sentence, max_tokens))
            continue
        candidate = f"{current} {sentence}".strip()
        if current and estimate_tokens(candidate) > max_tokens:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _split_by_words(text: str, max_tokens: int) -> list[str]:
    budget = max_tokens * CHARS_PER_TOKEN
    pieces: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > budget:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _pack(blocks: Sequence[str], max_tokens: int) -> list[str]:
    packed: list[str] = []
    current: list[str] = []
    for block in blocks:
        candidate = "\n\n".join([*current, block])
        if current and estimate_tokens(candidate) > max_tokens:
            packed.append("\n\n".join(current))
            current = [block]
        else:
            current.append(block)
    if current:
        packed.append("\n\n".join(current))
    return packed
