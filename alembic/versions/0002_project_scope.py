"""Add project scope to documents.

Revision ID: 0002_project_scope
Revises: 0001_initial
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_project_scope"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable project column and its lookup index."""
    op.add_column("documents", sa.Column("project", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_documents_project_library_status", "documents", ["project", "library", "status"]
    )


def downgrade() -> None:
    """Drop the project index and column."""
    op.drop_index("ix_documents_project_library_status", table_name="documents")
    op.drop_column("documents", "project")
