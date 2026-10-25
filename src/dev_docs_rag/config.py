"""Runtime configuration loaded from environment variables and ``.env``."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All knobs the service reads. Defaults target a local docker compose stack."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://devdocs:devdocs@localhost:5432/devdocs"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "amqp://devdocs:devdocs@localhost:5672//"
    celery_result_backend: str = "redis://localhost:6379/1"

    knowledge_dir: Path = Path("knowledge")

    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = Field(default=384, gt=0)
    embedding_batch_size: int = Field(default=32, gt=0)

    chunk_max_tokens: int = Field(default=600, gt=0)
    search_top_k: int = Field(default=5, gt=0)
    search_max_top_k: int = Field(default=20, gt=0)
    search_candidates: int = Field(default=30, gt=0)
    rrf_k: int = Field(default=60, gt=0)
    cache_ttl_seconds: int = Field(default=3600, gt=0)

    git_clone_timeout_seconds: int = Field(default=300, gt=0)
    ingestion_max_retries: int = Field(default=3, ge=0)

    @model_validator(mode="after")
    def _check_search_limits(self) -> "Settings":
        if self.search_top_k > self.search_max_top_k:
            raise ValueError("SEARCH_TOP_K must be <= SEARCH_MAX_TOP_K")
        if self.search_candidates < self.search_top_k:
            raise ValueError("SEARCH_CANDIDATES must be >= SEARCH_TOP_K")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
