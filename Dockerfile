FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    FASTEMBED_CACHE_PATH=/models \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-group dev --no-install-project

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-group dev

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /models \
    && chown -R app:app /models /app
USER app

EXPOSE 8000

CMD ["uvicorn", "dev_docs_rag.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
