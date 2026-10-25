# Dev-Docs RAG

Локальный сервис семантического и полнотекстового поиска по документации библиотек. Режим — retrieval-only: внутри нет LLM, сервис только находит и отдаёт фрагменты с ссылкой на источник. Ответ формирует агент, который подключается к сервису через MCP.

Источник правды — git-каталог `knowledge/` с markdown-файлами и front-matter. Postgres — вторичный индекс, который полностью пересобирается командой `devdocs reindex`.

## Что умеет

- Ингест markdown из локальной папки: `devdocs ingest add`, копирование в `knowledge/<library>/<version>/` с формированием front-matter.
- Асинхронная индексация через RabbitMQ + Celery: одна задача — один файл, ретраи с backoff, dead-letter очередь.
- Идемпотентность по `content_hash`: повторный ингест неизменённого файла ничего не пересчитывает.
- Гибридный поиск: pgvector (cosine) + полнотекстовый поиск Postgres, слияние через reciprocal rank fusion (k=60).
- Фильтры `library`, `version`, `status`; по умолчанию только `approved`.
- Кэш поиска в Redis с ключом по `index_version`; при недоступном Redis поиск работает без кэша.
- Документы проекта рядом с библиотеками: требования, ADR и договорённости команды, отдельный фильтр `project`.
- MCP-сервер `devdocs-mcp` (stdio): инструмент `search_docs` проксирует поиск в API, чтобы агент вызывал базу как инструмент.
- HTTP API на FastAPI, health-check по Postgres, Redis и RabbitMQ.

## Чего не умеет (осознанно)

- Не генерирует ответы — LLM внутри нет.
- В MCP один инструмент — `search_docs`; `list_libraries` и `confidence` — этап 2.
- Нет аутентификации, интерфейса и реранкера.
- Не индексирует `.rst`/HTML: адаптеры запланированы.
- Не обновляется по расписанию.

## Архитектура

```mermaid
flowchart LR
    CLI[devdocs ingest / reindex] --> Q[(RabbitMQ\nindex_file)]
    API[POST /sources] --> Q
    Q --> W[Celery worker]
    W -->|chunk, embed, upsert| DB[(Postgres + pgvector\nchunks.tsv)]
    S[GET /search] --> C[(Redis\ncache)]
    S --> DB
    S --> R[results + source_url]
```

Два потока:

- **Ингест.** CLI или `POST /sources` копирует файлы в `knowledge/` и публикует по задаче на файл. Воркер читает front-matter, режет по заголовкам, считает эмбеддинги, пишет документ и чанки, поднимает `index_version`.
- **Поиск.** `GET /search` берёт top-30 по вектору и top-30 по FTS, сливает RRF, отдаёт `top_k`. Результат и эмбеддинг запроса кэшируются; ключ включает версию индекса.
- **MCP.** `devdocs-mcp` (stdio) вызывает `GET /search` по HTTP; агенту не нужны ни БД, ни модель, ни ключи.

## Быстрый старт

```bash
bash scripts/bootstrap.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

Скрипт копирует `.env.example` в `.env`, собирает образ, поднимает Postgres + pgvector, Redis, RabbitMQ, API и воркер, применяет миграции и ставит в очередь демо-корпус (FastAPI и Pydantic).

Проверка:

```bash
curl http://localhost:8000/health
```

```json
{"status":"ok","postgres":"ok","redis":"ok","rabbitmq":"ok"}
```

Первый поиск загружает модель эмбеддингов в процесс API и занимает несколько секунд. Дальше — десятки миллисекунд.

Management UI RabbitMQ: http://localhost:15672 (логин и пароль из `.env`).

Сброс: `docker compose down -v` удаляет базу и кэш модели, но каталог `knowledge/` на хосте остаётся. После сброса достаточно `docker compose up -d` и `devdocs reindex` (или повторного bootstrap, если корпус тоже нужно скачать заново).

## API

### POST /sources

Копирует markdown из локальной папки в `knowledge/` и ставит задачи в очередь. Отвечает `202`.

```bash
curl -X POST http://localhost:8000/sources \
  -H "Content-Type: application/json" \
  -d '{"library":"fastapi","version":"0.115","path":"/docs/fastapi","docs_dir":"docs/en/docs","license":"MIT"}'
```

```json
{"queued": 156}
```

Ошибки: `422`, если путь не каталог, в нём нет markdown или `library`/`version` не соответствуют slug (`[a-z0-9._-]`); `503`, если RabbitMQ недоступен.

### GET /search

Параметры: `q` (обязательный), `project`, `library`, `version`, `status` (по умолчанию `approved`), `top_k` (1–20, по умолчанию 5).

```bash
curl "http://localhost:8000/search?q=как+выполнить+код+при+старте+приложения&library=fastapi&top_k=2"
```

Ответ (текст сокращён):

```json
{
  "cached": false,
  "results": [
    {
      "chunk_id": 5195,
      "library": "fastapi",
      "version": "master",
      "tier": "official",
      "type": "doc",
      "status": "approved",
      "path": "fastapi/master/advanced/events.md",
      "heading_path": "Lifespan Events",
      "source_url": "https://github.com/tiangolo/fastapi/blob/master/docs/en/docs/advanced/events.md",
      "score": 0.0164,
      "text": "You can define logic (code) that should be executed before the application starts up..."
    }
  ]
}
```

`score` — сумма `1/(60 + rank)` по двум спискам. Одно попадание даёт `0.0164`, попадание и в векторный, и в полнотекстовый список — `0.0328`. Это не «похожесть», а сила голоса: RRF не сравнивает абсолютные расстояния, он сравнивает порядок.

### GET /health

Postgres обязателен: если он недоступен — `503`. Redis и RabbitMQ необязательны для поиска, поэтому при их отказе ответ остаётся `200`, но `status` становится `degraded`, а поле сервиса — `down`. Это позволяет мониторингу видеть проблему, не снимая сервис с обслуживания.

## Замеры

Корпус: 247 документов, 2753 чанка (FastAPI — 156/2025, Pydantic — 91/728). `index_version = 247`.

Латентность `GET /search` на этой машине (Windows, Docker Desktop, CPU):

- первый запрос после старта — 3.3 с (загрузка модели в процесс API);
- тёплый запрос — 26–30 мс;
- повторный запрос из кэша — 8–13 мс.

Качество на контрольных вопросах:

- «как выполнить код при старте приложения» → `Lifespan Events` первым;
- «how to add middleware» → `Advanced Middleware` первым, score `0.0328` (нашёлся обоими способами);
- «как валидировать поле модели» → `Basic model usage > Model methods and properties`;
- «проверка типов strict mode» → `Configure VS Code > Configure Pylance` — промах. Гибрид не лечит плохие формулировки: в документации Pydantic эта страница не про strict mode.

Формальной метрики recall@5 пока нет: eval-набор и `devdocs eval` — следующий этап.

## Конфигурация

Переменные приложения читаются `src/dev_docs_rag/config.py`; MCP-сервер читает две свои из окружения. Значения по умолчанию рассчитаны на локальный compose.

- `DATABASE_URL` — `postgresql+asyncpg://devdocs:devdocs@localhost:5432/devdocs`
- `REDIS_URL` — `redis://localhost:6379/0`
- `CELERY_BROKER_URL` — `amqp://devdocs:devdocs@localhost:5672//`
- `CELERY_RESULT_BACKEND` — `redis://localhost:6379/1`
- `KNOWLEDGE_DIR` — `knowledge`; в контейнере `/app/knowledge`
- `EMBEDDING_MODEL` — `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- `EMBEDDING_DIM` — `384`; должна совпадать с `vector(384)` в миграции, иначе приложение не стартует
- `EMBEDDING_BATCH_SIZE` — `32`
- `CHUNK_MAX_TOKENS` — `600` (оценка как `длина / 4`, без токенизатора)
- `SEARCH_TOP_K` — `5`, `SEARCH_MAX_TOP_K` — `20`
- `SEARCH_CANDIDATES` — `30` кандидатов от каждого вида поиска
- `RRF_K` — `60`
- `CACHE_TTL_SECONDS` — `3600`
- `GIT_CLONE_TIMEOUT_SECONDS` — `300` (для `devdocs ingest fetch`)
- `INGESTION_MAX_RETRIES` — `3`

Только для MCP-сервера (читаются в `mcp_server.py`, не в `config.py`):

- `DEVDOCS_SEARCH_URL` — `http://127.0.0.1:8000/search`; адрес API, который проксируется
- `DEVDOCS_TIMEOUT_SECONDS` — `10`; таймаут HTTP-запроса к API

Только для compose: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD` — из них собираются URL; `FASTEMBED_CACHE_PATH=/models` — кэш весов в volume.

## CLI владельца

```bash
devdocs ingest add --library fastapi --version 0.115 --source ./fastapi-docs --docs-dir docs/en/docs --license MIT
devdocs ingest fetch --library pydantic --version main --git-url https://github.com/pydantic/pydantic --ref main --docs-dir docs
devdocs reindex
```

`ingest add` — основной режим по ТЗ. `ingest fetch` — расширение: клонирует репозиторий, чтобы демо воспроизводилось одной командой; в ТЗ git-url отнесён к бэклогу.

`reindex` ставит в очередь все файлы `knowledge/`. Признак актуальности — отпечаток из тела, метаданных и имени модели эмбеддингов, поэтому `reindex` действительно пересчитывает векторы после смены модели и подхватывает правки `status`/`license`.

### Документы проекта

Кроме документации библиотек база хранит документы конкретного проекта: требования, ADR, договорённости команды. Они лежат отдельно и в общий поиск не попадают.

```bash
devdocs ingest add --project myapp --source ./docs/adr
```

`--library` и `--version` в этом режиме можно не указывать — подставятся имя проекта и `current`. Файлы попадают в `knowledge/_projects/myapp/`, во front-matter добавляются `project: myapp` и `tier: own`.

Поиск:

```bash
curl "http://localhost:8000/search?q=session.query&project=myapp"
```

Без `project` возвращаются только общие библиотечные документы; с `project` — документы этого проекта плюс общие. Чужие проектные документы в выдачу не попадают.

Репозиторий проекта остаётся первичным источником правил (`QWEN.md`, `docs/adr`), база — поисковая копия. Правило, которое агент обязан соблюдать всегда, должно жить в инструкциях, а не только в RAG.

Команды удаления пока нет: проект убирается через `DELETE FROM documents WHERE project = 'myapp'` плюс удаление каталога, либо пересозданием базы (`docker compose down -v`) и `reindex`.

## MCP-сервер

`devdocs-mcp` — отдельный stdio-процесс, который агент запускает сам. Он не ходит в БД и не грузит модель: единственный инструмент `search_docs` проксирует запрос в `GET /search`. Поэтому API должен быть запущен.

Подключение в `~/.qwen/settings.json`:

```json
"mcpServers": {
  "dev-docs-rag": {
    "command": "C:\\Users\\<user>\\PycharmProjects\\dev-docs-rag\\.venv\\Scripts\\devdocs-mcp.exe",
    "env": {
      "DEVDOCS_SEARCH_URL": "http://127.0.0.1:8000/search",
      "DEVDOCS_TIMEOUT_SECONDS": "10"
    },
    "trust": true
  }
}
```

`command` — абсолютный путь к `devdocs-mcp.exe`; он появляется после `uv sync`. `trust: true` отключает подтверждение запуска. После правки конфига Qwen Code нужно перезапустить, затем проверить `/mcp`.

Инструмент:

- `search_docs(query, library?, version?, project?, top_k?)` — `query` обязателен, `top_k` обрезается до 1–20;
- возвращает JSON-строку с `results`; в каждом элементе `chunk_id`, `project`, `library`, `version`, `heading_path`, `source_url`, `score`, `text`;
- если API недоступен, поднимает ошибку с подсказкой, а не возвращает пустой результат.

Правила для агента — когда вызывать, как ссылаться, что делать при промахе — лежат в `QWEN.md` (шаблон из раздела 10 ТЗ). `chunk_id` меняется после переиндексации, поэтому для ссылок используется `source_url`.

## Решения и почему

- **uv вместо Poetry.** Репозиторий уже был на uv; один lock-файл, быстрая установка, `uv sync --frozen` в CI. Отклонение от ТЗ зафиксировано здесь.
- **ruff format вместо black.** Один инструмент и один конфиг на линт и формат. Black удалён вместе с зависимостями.
- **`knowledge/` как источник правды.** Файлы видно в git, их можно ревьюить и откатывать. База пересобирается из каталога, а не наоборот.
- **Задача на файл, а не на репозиторий.** Ретрай переобрабатывает один файл; падение одного документа не блокирует остальные.
- **`index_version` вместо инвалидации по префиксу.** Счётчик в БД попадает в ключ кэша: старые ключи перестают совпадать сами, без `SCAN` и удаления. Растёт на каждый успешно проиндексированный файл, поэтому во время ингеста кэш временно холодный — это осознанный компромисс.
- **Гибридный поиск, а не только вектор.** Вектор промахивается на редких терминах и точных именах; FTS их ловит. RRF не требует калибровки скоров между разными метриками.
- **`to_tsvector('simple', ...)`.** Стемминг `english` ломает русские запросы, а запросы к английской документации формулируются по-русски. `simple` не стеммит, зато одинаково относится к обоим языкам.
- **HNSW оставлен.** ТЗ предлагает решать по EXPLAIN; на 2.7k чанков выигрыш невелик, но индекс уже есть и не мешает. На большом корпусе фильтры по `library`/`version` могут дать меньше `top_k`, чем просили, — известное ограничение pgvector.
- **Миграции отдельным сервисом.** Если накатывать их в команде API, две реплики устроят гонку `CREATE TABLE` и одна упадёт.
- **Redis — ускоритель, не зависимость.** Все операции кэша ловят `RedisError`: без кэша поиск медленнее, но жив.
- **Локальные эмбеддинги.** Запуск без ключей и без сети для ревьюера. Модель компактная: `multilingual-e5-small` в fastembed нет, `e5-large` (1024) тяжелее для CPU. Апгрейд — миграция размерности + `reindex`, это одна команда.
- **Front-matter в файле.** Метаданные лежат рядом с текстом и ревьюятся вместе с ним; отдельная таблица-справочник разъехалась бы с файлами.

## Надёжность

- Временные ошибки (сеть, таймаут клона) — ретраи `2^attempt` до `INGESTION_MAX_RETRIES`.
- Постоянные ошибки (битый front-matter, нет файла) — `Reject(requeue=False)` → `index_file.dlq`. Очередь и exchange объявляет one-shot сервис `topology`; у DLQ TTL 7 дней, дальше сообщения удаляются, а восстановление идёт через `reindex`.
- `acks_late=True` и `task_reject_on_worker_lost=True`: падение воркера не теряет сообщение.
- Идемпотентность по хэшу тела документа.
- Если RabbitMQ недоступен, `POST /sources` отвечает `503`, а не делает вид, что задача поставлена.

## Тесты и CI

```bash
uv sync
docker compose up -d db redis rabbitmq
uv run pytest -m unit          # без сервисов
uv run pytest -m integration   # Postgres devdocs_test, Redis db 15
uv run pytest --cov=src --cov-report=term-missing
```

- 65 тестов: 39 unit, 26 integration.
- Покрытие 82.4%, порог в CI — 80%. MCP-сервер проверяется вручную и в покрытие не входит.
- `cli.py` и `seed.py` исключены из покрытия: тонкая обвязка без логики.
- Интеграционные тесты используют отдельную БД `devdocs_test`, `FakeEmbedder` и перехват `.delay`; RabbitMQ для них не нужен.
- CI: `.github/workflows/ci.yml` — lint, тесты с сервисами pgvector/redis/rabbitmq и сборка образа (только на основной ветке); прогон зелёный. `.gitlab-ci.yml` оставлен с теми же стадиями для GitLab. Пуш образа не настроен: нет registry-переменных.

## Ограничения

- Качество зависит от формулировки запроса: «strict mode» уводит в страницу про VS Code. Нужен eval-набор, а не вера в демо.
- `.rst` не индексируется; конвертер `services/rst.py` написан и покрыт тестами, но в ингест не подключён (этап 4 по ТЗ).
- HNSW с фильтрами может вернуть меньше `top_k`; лечится `hnsw.iterative_scan` в pgvector 0.8.
- Модель загружается в процесс API лениво: первый запрос после старта медленный.
- Аутентификации нет; сервис рассчитан на localhost. Порты опубликованы только на `127.0.0.1`, иначе без аутентификации доступ к API означал бы доступ к чтению файлов машины через `POST /sources`.
- Проектные документы не изолированы жёстко: один индекс, и единственная граница — фильтр `project`. Для чужих секретов нужен отдельный стек compose.
- MCP-сервер требует запущенного API: без него инструмент возвращает ошибку, а не пустой список.
- `chunk_id` нестабилен между индексациями: после `reindex` документы пересоздаются, ссылаться нужно на `source_url`.
- `docs/` из сторонних репозиториев не коммитятся: `knowledge/` в `.gitignore`, лицензии фиксируются во front-matter.

## Roadmap (из ТЗ v0.2)

- **eval и recall@5** (этап 2). 20+ вопросов с ожидаемыми фрагментами, сравнение vector/hybrid. Без метрики улучшения недоказуемы.
- **`query_log` и `devdocs gaps`** (этап 2/бэклог). Какие запросы провалились — это backlog пополнения базы.
- **`confidence`, `hint` и параметр `status`** (этап 2). Пороги на сырых сигналах, а не на RRF: RRF говорит о порядке, не о близости. Тогда же в MCP появится `list_libraries`.
- **pending + ревью + `allowed_domains`** (бэклог). Ручное пополнение вместо автопостинга: качество, дубли, доверие.
- **Веб-фоллбэк и автопополнение** (бэклог). Самая ценная и самая рискованная часть.
- **Версии и свежесть** (бэклог). Сейчас версия — это строка из front-matter, без проверки актуальности.
- **Адаптеры rst/HTML** (этап 4). SQLAlchemy и Alembic сейчас вне корпуса.
- **Реранкер, аутентификация, UI, `sync --lockfile`** — после MVP.

## Лицензии

Тексты документации принадлежат их авторам и не хранятся в репозитории. `knowledge/` в `.gitignore`; при ингесте лицензия источника попадает во front-matter. Перед публикацией корпуса проверяйте лицензии отдельных проектов.
