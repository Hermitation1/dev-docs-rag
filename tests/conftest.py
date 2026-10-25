"""Test environment setup.

Environment variables must be set before ``dev_docs_rag.config`` is imported,
because :class:`Settings` is cached for the whole process.
"""

import os

DEFAULT_DATABASE_URL = "postgresql+asyncpg://devdocs:devdocs@localhost:5432/devdocs"


def _test_database_url() -> str:
    configured = os.environ.get("TEST_DATABASE_URL")
    if configured:
        return configured
    base = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    prefix, _, name = base.rpartition("/")
    return f"{prefix}/{name.split('?')[0]}_test"


TEST_DATABASE_URL = _test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
