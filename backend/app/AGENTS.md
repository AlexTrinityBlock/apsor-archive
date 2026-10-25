# backend/app — Agent Guide

This package contains the runnable backend: the FastAPI assembly, shared infrastructure adapters, cross-cutting helpers, and the vertical slices that implement archive behavior. It is the implementation boundary behind `backend/README.md`.

## Purpose

Keep application assembly, infrastructure, and business slices separate so a feature can change without turning `main.py` or a global utility module into a second architecture.

## Architecture

- `main.py` is the composition shell. `create_app()` installs lifespan resources, exception handlers, middleware, routers, and the SPA fallback. `cli.py` starts the API; `worker.py` starts the durable-ingestion process.
- `app.state` owns process-wide adapters: `db`, `cache`, `storage`, `secret_cipher`, `ai_runtime`, `ingest_worker`, and `settings`. Tests may replace `agent_chat_generator`, `web_research_service`, or `provider_tester`.
- `dependency/` holds dependencies shared across slices. Today it exposes the authenticated owner guard; it is not a home for feature services.
- `infrastructure/` adapts external systems: config, async database/Alembic, cache, local storage, AI/embeddings, web clients, security, and logging. Adapters implement slice protocols but must not own archive policy.
- `module/` contains vertical slices: `auth`, `knowledge`, `agent`, `prompt`, and `web_research`. A slice may contain `domain/` (pure rules), `model/` (SQLAlchemy), `schema/` (Pydantic HTTP contracts), `protocol/` (ports), `repository/` (SQL), `service/` (orchestration), `router/` (HTTP), `exception/`, and `dependencies.py`.
- `module/*/dependencies.py` is the allowed cross-slice assembly point. Routers must receive services from dependencies rather than constructing repositories directly.
- `shared/` contains only genuinely cross-cutting primitives: the exception registry, the generic list envelope, shared time, and text n-gram helpers. It must not absorb slice-specific logic.
- All ORM models share the declarative base in `infrastructure/database/base.py`. The model package exports are imported by Alembic and tests, so a new model must be reachable through the owning `model/__init__.py`.
- The request database session is created by `get_db_session` and committed once at request exit. Streaming agent turns and long-running workers must instead use `app.state.db.session_factory()` in short transactions.
- Authentication is mounted as a router-level dependency in `main.py`. Do not add a second session-cookie parser or an alternative owner check in a feature router.
- `AiRuntime` is the single resolved view of chat, embedding, web-search, and web-fetch providers. Feature code should ask it for clients/config instead of reading provider rows or environment keys directly.
- Stable errors are registered once during app creation. Every slice's `exception/handler.py` maps its domain exceptions to HTTP status plus a stable code; `shared/exception/registry.py` renders the envelope.

## Key files

- `main.py` — app factory, lifespan, middleware, protected/public router mounting, SPA.
- `cli.py`, `worker.py` — executable entrypoints and worker lifecycle.
- `dependency/auth.py` — resolves the HttpOnly session cookie into the owner principal.
- `infrastructure/database/session.py` — engine/session factory and commit boundary.
- `infrastructure/ai/runtime.py` — four-capability provider snapshot.
- `infrastructure/config/settings.py` — settings and secret-file precedence.
- `shared/exception/registry.py` — error and validation serialization.
- `module/knowledge/dependencies.py`, `module/agent/dependencies.py`, `module/auth/dependencies.py`, `module/prompt/dependencies.py`, `module/web_research/dependencies.py` — assembly roots.
- `module/agent/AGENTS.md` and `module/knowledge/AGENTS.md` — deeper rules for the two largest slices.

## Conventions

- Place behavior in the slice that owns the concept. A route-only helper stays beside its router; a reusable domain rule belongs in `domain/`, not in a router.
- Keep dependency direction inward: router → service → protocol/repository/domain. Composition roots may import across slices; routers and services should not reach into another slice's repository or call another slice's router.
- Give services protocols for external collaborators and repositories so tests can inject fakes. Concrete classes are wired in `dependencies.py`.
- Do not commit inside a request-scoped repository or service. Flush for generated ids and let the request boundary commit. Agent and worker code that owns its transaction scope is the explicit exception.
- Define request contracts with types and bounds, use `extra="forbid"` for closed write payloads, and return explicit response models with stable `operation_id`s. Preserve error envelopes.
- Raise domain exceptions from services. Register them in the slice handler; do not convert them into generic `HTTPException` at the router.
- Keep provider and secret handling centralized. Never log API keys or return ciphertext; errors should be safe for the client.
- Use `async` database and HTTP calls throughout. CPU-heavy extraction belongs in the worker's bounded executor.
- Rebuild the checked-in OpenAPI/Orval artifacts after any route or schema change. Do not patch generated TypeScript.
- When adding a model, update the slice model exports, a new Alembic revision, and migration verification. `create_all` in tests is not a migration test.

## Verification

```bash
cd backend
uv run ruff check app
uv run mypy app
PYTHONUNBUFFERED=1 uv run pytest -q
```

For a focused change, run the owning slice's tests first, then the full suite. Tests require the local disposable PostgreSQL test database; never point them at the live archive.

## Related guides

- [Parent](../AGENTS.md)
- [Agent slice](./module/agent/AGENTS.md)
- [Knowledge slice](./module/knowledge/AGENTS.md)
- [Backend tests](../tests/AGENTS.md)
