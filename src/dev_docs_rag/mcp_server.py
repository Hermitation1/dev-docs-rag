"""stdio MCP server that proxies documentation search to the HTTP API."""

import os

import httpx
from httpx import AsyncClient
from mcp.server import MCPServer

SEARCH_URL = os.getenv("DEVDOCS_SEARCH_URL", "http://127.0.0.1:8000/search")
SEARCH_TIMEOUT = float(os.getenv("DEVDOCS_TIMEOUT_SECONDS", "10"))


server = MCPServer("dev-docs-rag")


@server.tool()
async def search_docs(
    query: str,
    library: str | None = None,
    version: str | None = None,
    project: str | None = None,
    top_k: int = 5,
) -> str:
    """Найди фрагменты документации в локальной базе.

    Вызывай перед написанием кода с внешней библиотекой, чтобы опираться
    на проиндексированную документацию, а не на память модели. Если знаешь
    версию из lock-файла проекта, передай `library` и `version`.

    Возвращает JSON-строку с массивом `results`; в каждом элементе есть
    `chunk_id`, `project`, `library`, `version`, `heading_path`,
    `source_url`, `score` и `text`. Пустой массив означает, что совпадений
    в индексе нет. Если API недоступен, инструмент поднимает ошибку,
    а не возвращает пустой результат.
    """
    limit = min(max(top_k, 1), 20)
    params = {
        "q": query,
        "top_k": limit,
    }

    if library is not None:
        params["library"] = library
    if version is not None:
        params["version"] = version
    if project is not None:
        params["project"] = project

    try:
        async with AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            response = await client.get(SEARCH_URL, params=params)
            response.raise_for_status()
    except httpx.RequestError as e:
        raise RuntimeError("API недоступен, запусти docker compose up -d") from e
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"API ответил {e.response.status_code}: {e.response.text[:200]}") from e
    return response.text


def main() -> None:
    """Run the server over stdio so the agent can launch it as a child process."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
