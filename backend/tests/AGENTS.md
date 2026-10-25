# Backend Tests — Agent Guide

`backend/tests/` is the integration safety net for the public FastAPI behavior. Tests exercise the app through `TestClient`, a disposable PostgreSQL schema, and injected fakes for every external provider.

## Purpose

Prove HTTP contracts, persistence behavior, transaction boundaries, and error envelopes without calling a live archive, model provider, embedding service, or web API. The suite is intentionally small and behavioral rather than a mirror of every implementation function.

## Architecture

- `test_database` is a session fixture. It creates `apsor_archive_test` on the local development PostgreSQL instance if needed, drops and recreates the public schema, installs `pg_trgm`, creates `agent_commit_seq`, and builds all tables from SQLAlchemy metadata.
- The suite does not run Alembic. A migration regression is not caught here; validate migrations separately against development PostgreSQL.
- `clean_database` is autouse and runs before every test. It `TRUNCATE`s every tracked table with `RESTART IDENTITY CASCADE` and reseeds the four default system-prompt sections. Tests share one database and must be serial.
- `settings` points at the test database, a per-test temporary data directory, a memory cache, no SPA directory, no external AI, and no lifespan ingestion worker. Migrations and demo seeding are disabled.
- `anonymous_client` starts a clean app. `client` additionally creates the single owner account and keeps its session cookie. Most tests use `client`; auth-boundary tests use `anonymous_client`.
- The app factory is still the production `create_app`; only dependencies/resources are substituted. Fake seams are installed on `client.app.state`, not by patching transport internals.
- Provider seams are installed on `client.app.state` when a test needs them: `agent_chat_generator` uses `FakeChatGenerator`, `provider_tester` uses a deterministic probe, and `web_research_service` uses a local fake. No DeepSeek/OpenAI/Tavily request is made.
- Tests use fixed aware timestamps and API helpers where practical. Assertions favor HTTP status, parsed JSON, stable `error` codes, entry ordering, lineage, and persisted effects over exact human-readable detail strings.
- `pyproject.toml` sets `filterwarnings = ["error"]` and strict markers. A new warning fails the test; do not silence warnings globally.

## Key files

- `conftest.py` — database lifecycle, truncation, settings, owner setup, authenticated/anonymous clients.
- `helpers.py` — `create_text` and `create_memory` through the public API.
- `test_agent.py` — transcript replay, tools, SSE events, retry, compaction, fork, approval, page context, saved questions, web tools, cache usage.
- `test_file_library.py` — upload/text ingestion, paths, versions, folders, move/copy, async jobs, image fallback.
- `test_markdown_update.py` — optimistic version updates, historical/deleted 404s, schema limits.
- `test_versions.py` — lineage, current-only search, soft-delete visibility.
- `test_memories.py`, `test_search.py`, `test_summaries.py`, `test_timeline.py` — retrieval and memory behavior.
- `test_system.py` — auth/session, health, gzip, cache invalidation, provider registry.
- `test_system_prompt.py` — seeded sections, ordering, CRUD, frozen conversations, cache scope.
- `test_errors.py` — shared validation envelope and fail-closed agent configuration.

## Conventions

- Use only the dedicated disposable test database. `conftest.py` drops its schema; never repoint it at the live archive or put production data in reach.
- Keep tests serial. They share tables and truncate between cases, so do not add `pytest-xdist`, `-n auto`, or tests that assume isolated concurrent state.
- Exercise behavior through the public API with `TestClient`. Use direct SQL only for fixture setup or to verify a persistence invariant that the API cannot expose.
- Add a new table to `TRUNCATE_STATEMENT` in `conftest.py`; otherwise state leaks between tests. Import new model packages so `Base.metadata.create_all` sees them.
- Inject every external capability through the documented `app.state` seams or a dependency override. Never make a test depend on credentials, network access, or provider availability.
- If a test changes schema metadata, add/verify the corresponding Alembic migration outside this suite. Passing `create_all` does not mean a migration works.
- Keep the four system-prompt seeds in the fixture path aligned with migration seed data. Tests that need different prompt rows should create/edit them through the API.
- Freeze or pass explicit time values for time-sensitive behavior. Use `tmp_path`/the settings fixture for files; never write into `backend/data`.
- Assert stable status/code contracts and durable rows. Avoid asserting incidental log text, stack traces, or provider wording.
- When adding coverage, extend the matching test module rather than creating a second suite with duplicate fixtures. Keep focused tests readable and independent.
- Do not hard-code historical test counts from the README; coverage evolves. The authoritative test list is the files under `backend/tests/`.

## Verification

```bash
# From the repository root: start the disposable local PostgreSQL dependency
docker compose -f docker-compose.dev.yml up -d --wait

cd backend
PYTHONUNBUFFERED=1 uv run pytest -q
uv run pytest -q tests/test_agent.py
uv run ruff check . && uv run mypy app
```

The full suite must run serially with warnings treated as errors. Missing PostgreSQL, failed schema setup, or a real provider call is a test-environment failure, not a reason to weaken the suite.

## Related guides

- [Parent](../AGENTS.md)
- [Application package](../app/AGENTS.md)
- [Agent slice](../app/module/agent/AGENTS.md)
- [Knowledge slice](../app/module/knowledge/AGENTS.md)
