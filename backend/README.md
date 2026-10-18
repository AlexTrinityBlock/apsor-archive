# DendroMatrix Backend

FastAPI service for the DendroMatrix knowledge and memory archive.

## Run

```bash
uv sync
uv run alembic upgrade head
uv run dendromatrix --host 127.0.0.1 --port 8000 --reload
```

The API expects PostgreSQL and Valkey. The repository root has
`docker-compose.dev.yml` for both:

```bash
docker compose -f ../docker-compose.dev.yml up -d --wait
```

Default settings:

- `DENDRO_DATABASE_URL=postgresql+psycopg://dendro:dendro@127.0.0.1:55432/dendromatrix`
- `DENDRO_CACHE_URL=redis://127.0.0.1:56379/0`
- `DENDRO_DATA_DIR=backend/data`
- `DENDRO_STATIC_DIR=frontend/dist`
- `DENDRO_TIMEZONE=Asia/Taipei`

Every setting is prefixed with `DENDRO_`. The app also reads `.env` and
`.secrets/deepseek.env` for local development.

## AI

Set `DENDRO_DEEPSEEK_API_KEY` to enable `POST /api/v1/ask` and AI-generated
memory summaries. The default model is `deepseek-flash`. Without a key:

- summaries use the deterministic extractive fallback (`generator=extractive`);
- `/api/v1/ask` returns `503 ai_not_configured`.

## Account and sessions

The first visit creates the single owner account through
`POST /api/v1/auth/setup`. Passwords are hashed with Argon2; sessions are opaque
cookies whose SHA-256 hash is stored in `user_session`. The cookie is HttpOnly and
SameSite=Lax; set `DENDRO_COOKIE_SECURE=true` behind HTTPS. Every knowledge and
media endpoint requires the session; `/api/v1/health` and `/api/v1/auth/*` are
public. There is no password recovery, by design.

## Database

Alembic owns the schema. The initial migration creates `pg_trgm` and the seven
tables: `file`, `tree_node`, `chunk`, `chunk_ngram`, `memory`,
`memory_summary`, and `alembic_version`.

```bash
uv run alembic revision --autogenerate -m "change"
uv run alembic upgrade head
```

## Layout

```text
app/
  main.py
  shared/                  error registry, list envelope
  infrastructure/
    ai/                    DeepSeek client
    cache/                 Valkey + resilient memory fallback
    config/                settings
    database/              async engine, request session, migrations
    embedding/             hosted embedding client
    files/                 local original-byte storage
    logger/
  module/knowledge/
    domain/                pure chunking, n-gram, timeline, summary logic
    model/                 SQLAlchemy models
    repository/            SQL and retrieval queries
    service/               orchestration
    router/                HTTP adapters
    schema/                Pydantic request/response contracts
    exception/             stable domain errors
    dependencies.py        composition root
```

## Checks

```bash
uv run ruff check .
uv run mypy app
PYTHONUTF8=1 uv run bandit -r app -c pyproject.toml
uv run pip-audit
PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/dendromatrix-pytest.log
```

The tests use a real PostgreSQL database named `dendromatrix_test` on the same
instance. They run sequentially, reset tables between tests, and treat warnings
as errors. There are exactly ten tests.
