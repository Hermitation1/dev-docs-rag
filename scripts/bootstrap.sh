#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    cp .env.example .env
fi

docker compose up -d --build
docker compose run --rm api python -m dev_docs_rag.seed

echo "Stack is up. Health: http://localhost:8000/health"
echo "First search loads the embedding model and may take a few seconds."
