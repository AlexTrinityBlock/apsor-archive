# backend/ — Agent Guide

The backend owns the HTTP API, authentication, PostgreSQL persistence, durable ingestion, retrieval, AI provider adapters, and the persistent archive agent. `backend/README.md` is the detailed contract; this guide explains where code belongs and which rules must survive changes.

## Purpose

Serve the Apsor Archive API and the committed SPA, process asynchronous ingest jobs, and expose the archive and agent behavior through one stable `application/json` and `text/event-stream` contract.

## Architecture

- `app/main.py` builds the FastAPI application. Its lifespan calls `app/bootstrap.py` to create the database, cache, progress bus, storage router, secret cipher, provider-error notices, and AI runtime; it also owns the RabbitMQ dispatch publisher, recovers incomplete agent runs, and optionally runs Alembic migrations. `app/worker.py` builds the same process state and runs the background loops.
- The API is versioned at `/api/v1`. Auth, health, and SPA assets are public; knowledge and prompt routers are mounted behind `require_authenticated`. The agent and ingest-progress routers stream SSE, so they are mounted behind `require_stateless_authenticated`, which authenticates without holding the request session for the stream's lifetime. Account management and global configuration routers additionally require `role='root'`.
- The codebase is organized as vertical slices under `app/module/`: `auth`, `knowledge`, `agent`, `prompt`, and `web_research`. Each slice owns its router, service, repository, protocol, domain, schema, exception, and model layers as needed. Account listing/create/disable/enable/reset live in the auth slice's account router/service.
- A normal request flows router → service → repository. Routers translate HTTP; services make decisions and coordinate transactions; repositories contain SQL and do not own business rules. Every private repository method takes the acting `user_id` explicitly or captures it in the repository instance.
- `app/module/*/dependencies.py` is each slice's composition root. It builds repositories, services, caches, provider clients, and worker helpers, and is the place to inject test seams. `app/dependency/` contains dependencies shared across slices: `get_current_user`, `require_authenticated`, `require_stateless_authenticated`, and `require_root`. Cross-slice wiring happens only in a `dependencies.py` or the entrypoint tier (`main.py`, `worker.py`, `bootstrap.py`).
- Adapters live in `app/infrastructure/`: async SQLAlchemy sessions and RLS context, Alembic runner, Valkey-compatible cache, local and R2 original-byte storage, DeepSeek/OpenAI-compatible/Anthropic chat and vision clients, embeddings (HTTP and the offline signed-hashing embedder), the RabbitMQ dispatch publisher/consumer (`queue/rabbitmq.py`), security primitives, DeepSeek/Tavily/Exa web access, and logging.
- AI is selected per capability through `AiRuntime` (`chat`, `embedding`, `web_search`, `web_fetch`). Database provider rows override environment defaults; secrets are encrypted with Fernet and never serialized back to clients. Chat is additionally per account: `app_user` holds the primary/auxiliary `chat_provider_config` row ids, free-text model/effort, and optional budgets, resolved by exact row id with no global chat fallback. Provider rows stay global root-write configuration, and a shared endpoint key rotates for every assigned account.
- PostgreSQL is authoritative. Alembic owns the schema and enables `pg_trgm`. The request session commits once on successful exit and rolls back on any exception. It starts as `apsor_app` with no user context; authentication sets `app.user_id` / `app.user_role` on the same transaction.
- Every private table is protected by forced row-level security. The runtime connects with the owning login but every request or scoped worker transaction that touches private data runs `SET LOCAL ROLE apsor_app` and sets the transaction-local context through the session helpers. The owner connection is reserved for explicit worker claim/recovery maintenance and maintenance-only owner-id enumeration; it must never read another account's archive content.
- Durable ingestion uses `file_ingest_job` plus `SELECT ... FOR UPDATE SKIP LOCKED`. The dedicated `apsor-archive worker` process (`make worker`) owns the queue, the RabbitMQ consumer, the chat-image cleanup sweep, and the conversation-history indexer. The API only enqueues jobs and publishes RabbitMQ wake-ups; RabbitMQ is an optional latency hint and PostgreSQL stays the only job ledger. `APSOR_INGEST_WORKER_ENABLED=true` (default `false`) is an opt-in single-process development mode that runs the same loops in the API lifespan. The worker claims across accounts with a maintenance session, then processes each job inside the owner's `user_session`. The deprecated synchronous `POST /files` (`uploadFile`) and `POST /files/text` still extract or embed inside the request; clients should use `uploadFileAsync`.
- Agent SSE and tool calls use a scoped `user_session` rather than the request session, so a stream does not pin a database connection and never loses the owner's RLS context. Runtime settings are loaded as immutable snapshots in short-lived system sessions.
- Every domain exception is registered with `ExceptionRegistry`. Unexpected exceptions still become the shared JSON envelope; request validation becomes `400 invalid_request`, not FastAPI's default 422.

## Key files

- `app/main.py` — application factory, lifespan resources, middleware, router mounting, SPA fallback.
- `app/cli.py` / `app/worker.py` — `apsor-archive` API and worker entrypoints.
- `app/bootstrap.py` — process state and background loops shared by the API lifespan and the worker.
- `app/dependency/auth.py` — authenticated, stateless (SSE), and root-only guards used by protected routers.
- `app/infrastructure/database/session.py` — engine, session factory, RLS helpers (`public_session`, `user_session`, `system_session`, `maintenance_session`, `commit_and_reapply`), and the request transaction boundary.
- `app/infrastructure/config/settings.py` — all `APSOR_*` settings, storage backend selection, and local env-file loading.
- `app/infrastructure/files/` — local/R2 storage adapters, router, and provider-safe errors.
- `script/` — operational entrypoints: OpenAPI export, storage and chat-attachment migrations, and the Wikipedia sample ingester.
- `app/infrastructure/ai/runtime.py` — four-capability provider snapshot and reload behavior.
- `app/shared/exception/registry.py` — global error and validation envelope.
- `app/module/auth/router/account_router.py` — root-only account management.
- `app/module/*/dependencies.py` — per-slice assembly roots.
- `alembic/versions/` — ordered schema history; never treat model metadata as migration proof.
- `tests/conftest.py` — migrated disposable PostgreSQL test database, RLS verification, and deterministic root/user fixtures.

## Conventions

- Add behavior to the owning slice. Do not put business logic in `main.py`, `app/dependency/`, or a shared utility module merely to avoid a slice boundary.
- Depend on protocols for adapters and repositories where the slice defines one. Keep concrete SQLAlchemy repositories behind the service boundary; do not import another slice's repository or service into a router.
- Do not commit inside request-scoped repositories or services. Flush when later logic needs an identity; let `get_db_session` own the commit/rollback. Long-lived workflows may use their own explicit session/transaction boundary.
- Use the scoped session helpers, never `session_factory()` directly for private data. `public_session()` is for auth status/setup/login/logout and health; `user_session(user_id, role)` for authenticated services, agent tools, and worker job work; `system_session()` for global config reads/writes. `maintenance_session()` is only for worker claim/stale recovery, agent startup recovery, and maintenance-only cross-user enumeration that returns owner ids rather than archive content (for example the global embedding reindex). Ordinary request paths must never use it, and any workflow that gets an owner id must switch to that owner's `user_session` before reading or writing private rows.
- `SET LOCAL ROLE` and `set_config(..., true)` end at the transaction boundary. A bare `session.commit()` inside a scoped workflow silently returns the connection to the owning login and bypasses RLS. Use `commit_and_reapply(session, user_id, role)` for every mid-workflow checkpoint.
- A repository constructed for one account must never be reused for another. `AgentRepository` and short-session repositories capture `user_id`; the SSE stream re-applies it to every later transaction. Cache keys and cache versions for private data include `user_id`.
- Root checks are defense in depth, not the data boundary. Root-only routers must still call `require_root`, and private queries must still be owner-scoped even when the caller is root.
- Keep route handlers thin: typed request/response schemas, explicit `operation_id`, stable status codes, and domain errors raised by services.
- Add a domain exception and register it in the slice's exception handler rather than returning ad-hoc JSON. Never leak provider stack traces, ciphertext, SQL, or secret values in responses.
- New configuration belongs in `Settings` with the `APSOR_` prefix. Seed defaults may come from the environment, but mutable runtime limits must have one database source of truth and validation that matches PostgreSQL constraints. R2 credentials are `SecretStr` values loaded from `.secrets/r2.env`; never log them or return them.
- Schema changes require an Alembic revision, deterministic constraint names, and both upgrade and downgrade validation. A new private table must also add `user_id`, composite owner-safe foreign keys, grants for `apsor_app`, and an RLS policy; a new global config table needs read-all/root-write policies. Register the table in `tests/conftest.py`.
- Use async I/O end to end. Blocking parsing, hashing, and file work belongs in the worker's bounded executor or `asyncio.to_thread`, not on the event loop. Storage writes go through the storage router so local and R2 rows can coexist during a migration.
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
uv run mypy app script
uv run lint-imports                     # architecture contracts in pyproject.toml
PYTHONUTF8=1 uv run bandit -q -r app script -c pyproject.toml
PYTHONUNBUFFERED=1 uv run pytest -q
uv run pip-audit                        # needs network; part of `make audit`
```

`mypy` runs with `ignore_missing_imports`, so it does not catch a stale first-party import after a module move; `lint-imports` and the test suite do. Keep the `ignore_imports` debt lists in `pyproject.toml` shrinking: remove an entry when its layering fix lands, and do not add one without a reason comment.

Run the suite serially. It shares one disposable test database (`APSOR_TEST_DATABASE_NAME`, default `apsor_archive_test`, must end with `_test`; give each parallel worktree its own name), builds it with `alembic upgrade head`, resets it before each test, verifies the `apsor_app` role/grants/policies, and treats warnings as errors. Migration downgrade is a separate check against a development database.

## Related guides

- [Parent](../AGENTS.md)
- [Application package](./app/AGENTS.md)
- [Tests](./tests/AGENTS.md)
