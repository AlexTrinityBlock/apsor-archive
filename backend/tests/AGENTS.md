# Backend Tests — Agent Guide

`backend/tests/` is the integration safety net for the public FastAPI behavior. Tests exercise the app through `TestClient`, a disposable PostgreSQL schema, and injected fakes for every external provider.

## Purpose

Prove HTTP contracts, persistence behavior, transaction boundaries, and error envelopes without calling a live archive, model provider, embedding service, or web API. The suite is intentionally small and behavioral rather than a mirror of every implementation function.

## Architecture

- `test_database` is a session fixture. It creates `apsor_archive_test` on the local development PostgreSQL instance if needed, drops and recreates the public schema, runs `alembic upgrade head` as the owning login, and verifies the `apsor_app` role, grants, RLS flags, and policies. `Base.metadata.create_all` is deliberately not used: it cannot reproduce the role or policies requests depend on.
- The suite therefore executes the migration upgrade chain, but not a downgrade. Validate downgrade separately against development PostgreSQL.
- `clean_database` is autouse and runs before every test. It truncates every classified application table with `RESTART IDENTITY CASCADE`, resets `agent_commit_seq`, and reseeds the four default system-prompt sections. Tests share one database and must be serial.
- `settings` points at the test database, a per-test temporary data directory, a memory cache, no SPA directory, no external AI, no R2 storage, and no lifespan ingestion worker. In-app migrations are disabled because the fixture already ran Alembic.
- `anonymous_client` starts a clean app. `client` additionally creates the bootstrap root account and keeps its session cookie. `root_account` exposes that identity; `client_factory` / `user_client_factory` create independent cookie jars and normal accounts, optionally keeping `must_change_password=true` or completing the forced change. Most tests use `client`; auth-boundary tests use `anonymous_client`.
- The app factory is still the production `create_app`; only dependencies/resources are substituted. Fake seams are installed on `client.app.state`, not by patching transport internals.
- Provider seams are installed on `client.app.state` when a test needs them: `agent_chat_generator` uses `FakeChatGenerator`, `provider_tester` uses a deterministic probe, and `web_research_service` uses a local fake. No DeepSeek/OpenAI/Tavily request is made.
- `owner_engine` is the privileged migration/truncation/fixture connection. `rls_connection(...)` opens a rollback-only `apsor_app` transaction with optional `app.user_id` / `app.user_role`; use it for direct-SQL RLS proof instead of querying as the owner.
- Tests use fixed aware timestamps and API helpers where practical. Assertions favor HTTP status, parsed JSON, stable `error` codes, entry ordering, lineage, and persisted effects over exact human-readable detail strings.
- `pyproject.toml` sets `filterwarnings = ["error"]` and strict markers. A new warning fails the test; do not silence warnings globally.

## Key files

- `conftest.py` — migrated database lifecycle, role/grant/policy verification, truncation, root/user fixtures, RLS connection helper.
- `helpers.py` — `create_text` and `create_memory` through the public API.
- `test_agent.py` — transcript replay, tools, SSE events, retry, compaction, fork, approval, page context, saved questions, web tools, cache usage.
- `test_multi_user.py` — account lifecycle, forced password change, root-only routes, private-archive isolation, per-account prompts, direct-SQL RLS, checkpoint reapplication.
- `test_file_library.py` — upload/text ingestion, paths, versions, folders, move/copy, async jobs, image fallback, R2 adapter safety.
- `test_markdown_update.py` — optimistic version updates, historical/deleted 404s, schema limits.
- `test_versions.py` — lineage, current-only search, soft-delete visibility.
- `test_memories.py`, `test_search.py`, `test_summaries.py`, `test_timeline.py` — retrieval and memory behavior.
- `test_system.py` — auth/session, health, gzip, cache invalidation, provider registry.
- `test_system_prompt.py` — seeded sections, ordering, CRUD, frozen conversations, cache scope.
- `test_errors.py` — shared validation envelope and fail-closed agent configuration.

## Conventions

- Use only the dedicated disposable test database. `conftest.py` drops its schema; never repoint it at the live archive or put production data in reach.
- Keep tests serial. They share tables and truncate between cases, so do not add `pytest-xdist`, `-n auto`, or tests that assume isolated concurrent state.
- Exercise behavior through the public API with `TestClient`. Use direct SQL only for fixture setup or to verify a persistence invariant that the API cannot expose. For RLS proof, use `rls_connection` and let it roll back.
- Add a new application table to the correct `PRIVATE_TABLES` / `GLOBAL_TABLES` / `AUTH_TABLES` classification in `conftest.py`; the fixture compares the live catalog with that set and fails on drift. Truncation is derived from the catalog, so a new table cannot silently leak state.
- A new private table must arrive with `user_id`, owner-safe composite lineage foreign keys, grants, and an RLS policy in the same migration, plus a test that touches it. A new global config table needs read-all/root-write policies.
- Inject every external capability through the documented `app.state` seams or a dependency override. Never make a test depend on credentials, network access, provider availability, or R2.
- If a test changes schema metadata, add/verify the corresponding Alembic migration outside this suite. The fixture runs the upgrade chain, but it does not replace a downgrade check.
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
