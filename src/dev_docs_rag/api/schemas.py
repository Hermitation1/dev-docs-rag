"""Request and response models for the HTTP API."""

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    """Body of ``POST /sources``: a local documentation directory to ingest."""

    library: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)
    project: str | None = Field(default=None, max_length=64)
    path: str = Field(min_length=1, max_length=1024)
    docs_dir: str | None = Field(default=None, max_length=256)
    license: str = Field(default="unknown", max_length=128)
    source_url: str | None = Field(default=None, max_length=1024)


class SourceQueued(BaseModel):
    """How many files were copied into the knowledge directory and queued."""

    queued: int


class SearchResult(BaseModel):
    """One chunk in the search response."""

    chunk_id: int
    project: str | None
    library: str
    version: str
    tier: str
    type: str
    status: str
    path: str
    heading_path: str
    source_url: str
    score: float
    text: str


class SearchResponse(BaseModel):
    """Answer of ``GET /search``."""

    cached: bool
    results: list[SearchResult]
