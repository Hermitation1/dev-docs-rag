$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}

docker compose up -d --build
docker compose run --rm api python -m dev_docs_rag.seed

Write-Host "Stack is up. Health: http://localhost:8000/health"
Write-Host "First search loads the embedding model and may take a few seconds."
