# backend/ — Agent Guide

The backend owns the HTTP API, authentication, PostgreSQL persistence, durable ingestion, retrieval, AI provider adapters, and the persistent archive agent. `backend/README.md` is the detailed contract; this guide explains where code belongs and which rules must survive changes.

## Purpose

Serve the Apsor Archive API and the committed SPA, process asynchronous ingest jobs, and expose the archive and agent behavior through one stable `application/json` and `text/event-stream` contract.

## Architecture

- `app/main.py` builds the FastAPI application. Its lifespan creates the database, cache, storage, secret cipher, AI runtime, and ingestion worker; it also recovers incomplete agent runs and optionally runs Alembic migrations.
- The API is versioned at `/api/v1`. Auth, health, and SPA assets are public; knowledge, settings, prompt, and agent routers require the owner session.
- The codebase is organized as vertical slices under `app/module/`: `auth`, `knowledge`, `agent`, `prompt`, and `web_research`. Each slice owns its router, service, repository, protocol, domain, schema, exception, and model layers as needed.
- A normal request flows router → service → repository. Routers translate HTTP; services make decisions and coordinate transactions; repositories contain SQL and do not own business rules.
- `app/module/*/dependencies.py` is each slice's composition root. It builds repositories, services, caches, provider clients, and worker helpers, and is the place to inject test seams. `app/dependency/` contains dependencies shared across slices, currently the session guard.
- Adapters live in `app/infrastructure/`: async SQLAlchemy sessions, Alembic runner, Valkey-compatible cache, local original-byte storage, DeepSeek/OpenAI-compatible AI clients, embeddings, security primitives, Tavily access, and logging.
- AI is selected per capability through `AiRuntime` (`chat`, `embedding`, `web_search`, `web_fetch`). Database provider rows override environment defaults; secrets are encrypted with Fernet and never serialized back to clients.
- PostgreSQL is authoritative. Alembic owns the schema and enables `pg_trgm`. The request session commits once on successful exit and rolls back on any exception.
- Durable ingestion uses `file_ingest_job` plus `SELECT ... FOR UPDATE SKIP LOCKED`. A dedicated `apsor-archive worker` process should own the queue in production; the API lifespan worker is a local convenience controlled by `APSOR_INGEST_WORKER_ENABLED`.
- Agent SSE and tool calls use `app.state.db.session_factory()` rather than the request session, so a stream does not pin a database connection. Runtime settings are loaded as immutable snapshots in short-lived sessions.
- Every domain exception is registered with `ExceptionRegistry`. Unexpected exceptions still become the shared JSON envelope; request validation becomes `400 invalid_request`, not FastAPI's default 422.

## Key files

- `app/main.py` — application factory, lifespan resources, middleware, router mounting, SPA fallback.
- `app/cli.py` / `app/worker.py` — `apsor-archive` API and worker entrypoints.
- `app/dependency/auth.py` — owner-session guard used by protected routers.
- `app/infrastructure/database/session.py` — engine, session factory, and request transaction boundary.
- `app/infrastructure/config/settings.py` — all `APSOR_*` settings and local env-file loading.
- `app/infrastructure/ai/runtime.py` — four-capability provider snapshot and reload behavior.
- `app/shared/exception/registry.py` — global error and validation envelope.
- `app/module/*/dependencies.py` — per-slice assembly roots.
- `alembic/versions/` — ordered schema history; never treat model metadata as migration proof.
- `tests/conftest.py` — dedicated PostgreSQL test database and deterministic app fixtures.

## Conventions

- Add behavior to the owning slice. Do not put business logic in `main.py`, `app/dependency/`, or a shared utility module merely to avoid a slice boundary.
- Depend on protocols for adapters and repositories where the slice defines one. Keep concrete SQLAlchemy repositories behind the service boundary; do not import another slice's repository or service into a router.
- Do not commit inside request-scoped repositories or services. Flush when later logic needs an identity; let `get_db_session` own the commit/rollback. Long-lived workflows may use their own explicit session/transaction boundary.
- Keep route handlers thin: typed request/response schemas, explicit `operation_id`, stable status codes, and domain errors raised by services.
- Add a domain exception and register it in the slice's exception handler rather than returning ad-hoc JSON. Never leak provider stack traces, ciphertext, SQL, or secret values in responses.
- New configuration belongs in `Settings` with the `APSOR_` prefix. Seed defaults may come from the environment, but mutable runtime limits must have one database source of truth and validation that matches PostgreSQL constraints.
- Schema changes require an Alembic revision, deterministic constraint names, and both upgrade and downgrade validation. Tests use `Base.metadata.create_all`, so they cannot catch a bad migration.
- Use async I/O end to end. Blocking parsing, hashing, and file work belongs in the worker's bounded executor or `asyncio.to_thread`, not on the event loop.
- Any API contract change must regenerate the checked-in OpenAPI document and Orval client before the change is complete.
- Never run backend tests against a live archive. The integration suite creates and destroys the schema of a dedicated test database.

## Verification

```bash
# Start the local PostgreSQL/Valkey dependencies once
docker compose -f ../docker-compose.dev.yml up -d --wait

cd backend
uv sync
uv run alembic upgrade head
uv run ruff check .
uv run mypy app
PYTHONUTF8=1 uv run bandit -r app -c pyproject.toml
uv run pip-audit
PYTHONUNBUFFERED=1 uv run pytest -q
```

Run the suite serially. It shares one test database, resets it before each test, and treats warnings as errors. Migration upgrade/downgrade is a separate check against the development database.

## Related guides

- [Parent](../AGENTS.md)
- [Application package](./app/AGENTS.md)
- [Tests](./tests/AGENTS.md)
