# backend/app — Agent Guide

This package contains the runnable backend: the FastAPI assembly, shared infrastructure adapters, cross-cutting helpers, and the vertical slices that implement archive behavior. It is the implementation boundary behind `backend/README.md`.

## Purpose

Keep application assembly, infrastructure, and business slices separate so a feature can change without turning `main.py` or a global utility module into a second architecture.

## Architecture

- `main.py` is the composition shell. `create_app()` installs lifespan resources, exception handlers, middleware, routers, and the SPA fallback. `cli.py` starts the API; `worker.py` starts the durable-ingestion process; `bootstrap.py` builds the process state and background loops both share; `__main__.py` forwards `python -m app` to the CLI. These four entrypoint files are the only modules allowed at the package root besides `main.py`.
- `app.state` owns process-wide adapters: `db`, `cache`, `progress_bus`, `storage`, `secret_cipher`, `ai_runtime`, `provider_notice_service`, `job_notifier`, and `settings`. `ingest_worker` and `job_consumer` exist only when the opt-in in-API worker mode (`APSOR_INGEST_WORKER_ENABLED=true`) is on; the test fixtures attach an `ingest_worker` explicitly. Tests may replace `agent_chat_generator`, `web_research_service`, `provider_tester`, or `vision_extractor`.
- `dependency/` holds dependencies shared across slices. Today it exposes the authenticated account guard, its stateless SSE variant (`require_stateless_authenticated`), the forced-password-change guard, and the root guard; it is not a home for feature services.
- `infrastructure/` adapts external systems: config, async database/Alembic, cache and progress bus, local/R2 storage, AI chat/vision clients, embedding (HTTP and offline hashing), RabbitMQ dispatch (`queue/`), web clients, security, and logging. Adapters implement slice protocols but must not own archive policy.
- `module/` contains vertical slices: `auth`, `knowledge`, `agent`, `prompt`, `companion`, and `web_research`. A slice may contain `domain/` (pure rules), `model/` (SQLAlchemy), `schema/` (Pydantic HTTP contracts), `protocol/` (ports), `repository/` (SQL), `service/` (orchestration), `router/` (HTTP), `exception/`, and `dependencies.py`.
- `module/*/dependencies.py` is the allowed cross-slice assembly point. Routers must receive services from dependencies rather than constructing repositories directly. `uv run lint-imports` enforces the layer and slice contracts declared in `backend/pyproject.toml`; its `ignore_imports` lists are the documented debts (services that own short sessions, storage error types, model-catalog lookups, the history indexer's reuse of knowledge chunking/cache contracts, and model assignments touching `app_user`).
- `shared/` contains only genuinely cross-cutting primitives: the exception registry, the generic list envelope (`types/`), shared time, the history-window retrieval constants used by knowledge and agent (`retrieval.py`), text n-gram helpers, and the companion action vocabulary shared by the agent tool and the companion slice. It must not absorb slice-specific logic.
- Companion stories are database content, not code. `module/companion/lore/` (including `lore/seed/config.json` and `lore/seed/templates/`) is seed data applied by `seed_companion` from `bootstrap.open_process_state` (idempotent, advisory-locked, keeps root's edits and flags `upstream_seed_hash`). Services read presets, lore, canon, world docs, tunables, word lists, and templates only through the config/content/policy providers; never add a story string, word list, or tunable to Python. Admin writes must bump `companion_seed_state.content_version` (`CompanionWorldRepository.bump_content_version`) and invalidate the providers. `commit_and_reapply` also restores `app.admin_scope`.
- All ORM models import the declarative base from `infrastructure/database/base.py` directly; Alembic's `env.py` imports every slice's `model` package for metadata, so a new model must be reachable through the owning `model/__init__.py`.
- The request database session is created by `get_db_session`, starts as `apsor_app` with no owner context, and commits once at request exit. `get_current_user` applies `app.user_id`/`app.user_role` after resolving the cookie. Streaming agent turns and long-running workers must use `database.user_session(...)`, `database.system_session()`, or the explicit `maintenance_session(...)` helpers; never open a raw `session_factory()` for private data. Ingestion checkpoints must use `commit_and_reapply(...)`.
- Authentication is mounted as a router-level dependency in `main.py`. Do not add a second session-cookie parser or an alternative account/role check in a feature router. Root-only global settings use `require_root`; ordinary private data uses `require_authenticated`. Root's companion administration (`/admin/companions`) is the one route set that adds the `companion` admin scope on top of `require_root` (see `module/companion/dependencies.py::get_companion_admin_service`).
- `AiRuntime` is the single resolved view of chat, embedding, web-search, and web-fetch providers. Feature code should ask it for clients/config instead of reading provider rows or environment keys directly. Account chat calls go through `infrastructure/ai/user_models.py`, which resolves the assigned `chat_provider_config` row by id and never falls back to `runtime.chat_config` or another row; provider rows stay root-write.
- Stable errors are registered once during app creation. Every slice's `exception/handler.py` maps its domain exceptions to HTTP status plus a stable code; `shared/exception/registry.py` renders the envelope.

## Key files

- `main.py` — app factory, lifespan, middleware, protected/public router mounting, SPA.
- `cli.py`, `worker.py` — executable entrypoints and worker lifecycle.
- `bootstrap.py` — shared process state (`open_process_state` / `close_process_state`) and `BackgroundServices` for the worker loops.
- `dependency/auth.py` — resolves the HttpOnly session cookie into the account principal and applies the RLS context; exposes account/root guards.
- `infrastructure/database/session.py` — engine/session factory, RLS-scoped session helpers, request commit boundary, and checkpoint helper.
- `infrastructure/ai/runtime.py` — four-capability provider snapshot.
- `infrastructure/config/settings.py` — settings and secret-file precedence.
- `shared/exception/registry.py` — error and validation serialization.
- `module/knowledge/dependencies.py`, `module/agent/dependencies.py`, `module/auth/dependencies.py`, `module/prompt/dependencies.py`, `module/companion/dependencies.py`, `module/web_research/dependencies.py` — assembly roots.
- `module/agent/AGENTS.md` and `module/knowledge/AGENTS.md` — deeper rules for the two largest slices.

## Conventions

- Place behavior in the slice that owns the concept. A route-only helper stays beside its router; a reusable domain rule belongs in `domain/`, not in a router.
- Keep dependency direction inward: router → service → protocol/repository/domain. Composition roots may import across slices; routers and services should not reach into another slice's repository or call another slice's router.
- Give services protocols for external collaborators and repositories so tests can inject fakes. Concrete classes are wired in `dependencies.py`.
- Do not commit inside a request-scoped repository or service. Flush for generated ids and let the request boundary commit. Agent and worker code that owns its transaction scope must open it through the scoped session helpers; use `commit_and_reapply` when a workflow checkpoint must commit inside that scope.
- Define request contracts with types and bounds, use `extra="forbid"` for closed write payloads, and return explicit response models with stable `operation_id`s. Preserve error envelopes.
- Raise domain exceptions from services. Register them in the slice handler; do not convert them into generic `HTTPException` at the router.
- Keep provider and secret handling centralized. Never log API keys or return ciphertext; errors should be safe for the client.
- Use `async` database and HTTP calls throughout. CPU-heavy extraction belongs in the worker's bounded executor.
- Rebuild the checked-in OpenAPI/Orval artifacts after any route or schema change. Do not patch generated TypeScript.
- When adding a model, update the slice model exports, a new Alembic revision, and migration verification. The test fixture runs the real migration chain (including the `apsor_app` role, grants, and RLS policies); `Base.metadata.create_all` is deliberately not used.

## Verification

```bash
cd backend
uv run ruff check .
uv run mypy app script
uv run lint-imports
PYTHONUNBUFFERED=1 uv run pytest -q
```

For a focused change, run the owning slice's tests first, then the full suite. Tests require the local disposable PostgreSQL test database; never point them at the live archive.

## Related guides

- [Parent](../AGENTS.md)
- [Agent slice](./module/agent/AGENTS.md)
- [Knowledge slice](./module/knowledge/AGENTS.md)
- [Backend tests](../tests/AGENTS.md)
