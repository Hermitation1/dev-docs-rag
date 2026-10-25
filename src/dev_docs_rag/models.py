"""SQLAlchemy models: knowledge documents, chunks and the index version."""

from datetime import date, datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Fixed by the initial migration: changing it requires a new migration and a reindex.
EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    """Declarative base shared by every table."""


class DocumentStatus(StrEnum):
    """Whether the text can be trusted and returned to an agent."""

    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"


class Document(Base):
    """One markdown file from the knowledge directory."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("library", "version", "path", name="uq_documents_library_version_path"),
        Index("ix_documents_library_version_status", "library", "version", "status"),
        Index("ix_documents_project_library_status", "project", "library", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project: Mapped[str | None] = mapped_column(String(64), default=None)
    library: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(1024))
    source_url: Mapped[str] = mapped_column(String(1024))
    tier: Mapped[str] = mapped_column(String(16), default="official")
    type: Mapped[str] = mapped_column(String(32), default="doc")
    status: Mapped[str] = mapped_column(String(16), default=DocumentStatus.APPROVED.value)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    license: Mapped[str] = mapped_column(String(128), default="unknown")
    content_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[date | None] = mapped_column(Date, default=None)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class Chunk(Base):
    """A piece of a document with its embedding and full-text vector."""

    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ord: Mapped[int] = mapped_column(Integer)
    heading_path: Mapped[str] = mapped_column(String(512), default="")
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str] = mapped_column(String(128))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True)
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class IndexState(Base):
    """A single row holding the version of the current index."""

    __tablename__ = "index_state"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
