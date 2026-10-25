import pytest

from dev_docs_rag.services.rst import rst_to_markdown

pytestmark = pytest.mark.unit

SAMPLE = """\
Quick Start
===========

Some *text* with ``literal`` and a :class:`Widget`.

.. code-block:: python

    def handler():
        return 1

- first
- second
"""


def test_converts_sections_code_blocks_and_lists():
    markdown = rst_to_markdown(SAMPLE)

    assert "# Quick Start" in markdown
    assert "`literal`" in markdown
    assert "```python" in markdown
    assert "def handler():" in markdown
    assert markdown.count("```") == 2
    assert "- first" in markdown
    assert "- second" in markdown


def test_unknown_role_keeps_its_text():
    markdown = rst_to_markdown("See :class:`Widget` here.\n")

    assert "Widget" in markdown


def test_versionadded_directive_keeps_the_body():
    markdown = rst_to_markdown("Title\n=====\n\n.. versionadded:: 2.0\n\n    New behaviour.\n")

    assert "New behaviour." in markdown


def test_sphinx_only_directives_are_dropped():
    markdown = rst_to_markdown("Title\n=====\n\n.. currentmodule:: sqlalchemy.orm\n\nBody text.\n")

    assert "currentmodule" not in markdown
    assert "Body text." in markdown


def test_nested_sections_get_deeper_headings():
    markdown = rst_to_markdown("Top\n===\n\nIntro.\n\nSub\n---\n\nDetails.\n")

    assert "# Top" in markdown
    assert "## Sub" in markdown
