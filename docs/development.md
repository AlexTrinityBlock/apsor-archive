# Development

**English** · [繁體中文](zh-TW/development.md) · [简体中文](zh-CN/development.md)

### Local development

```bash
# 1. PostgreSQL + Valkey
docker compose -f docker-compose.dev.yml up -d --wait

# 2. API
cd backend
uv sync
uv run alembic upgrade head
uv run apsor-archive --reload

# 3. Frontend (second terminal)
cd frontend
bun install
bun run dev
```

The dev database is PostgreSQL on `127.0.0.1:55432` with role `apsor` and
database `apsor_archive`
(`postgresql+psycopg://apsor:apsor@127.0.0.1:55432/apsor_archive`). Vite runs on
<http://127.0.0.1:5173> and proxies `/api` to the API. To build the client that
the container serves:

```bash
cd frontend && bun run build
```

`./start.sh` is the shortest bare-metal path. Run `./start.sh setup --dev`
once to write a development `.env` (local storage by default), then
`./start.sh` starts the dev database/cache if Docker is available, syncs the
backend, and runs the API at <http://127.0.0.1:8000> together with the dedicated
ingestion worker; Ctrl+C stops both. Set `APSOR_START_WORKER=false` to run the
API alone. Run `cd frontend && bun run build` once before the first bare-metal
start. To try the S3 path locally, choose `rustfs` in the wizard and start the
dev store with `docker compose -f docker-compose.dev.yml --profile rustfs up -d`.

On Windows, `./start.sh` needs a bash shell. `./run-local.ps1` is the PowerShell
equivalent: it starts the dev database/cache if Docker is available, syncs the
backend, and serves the same URL. The app reads `.secrets/` itself, so the script
does not export those values. It also forces a `SelectorEventLoop`, because
psycopg's async mode rejects the `ProactorEventLoop` that uvicorn selects by
default on Windows.

```powershell
.\run-local.ps1            # http://127.0.0.1:8000
.\run-local.ps1 -Port 8080
```

### Generated API client and drift

The repository commits both `frontend/openapi.json` and the generated
`frontend/src/app/generated-apis-types/` client. A fresh clone and the Docker
build therefore work without a running backend. To change the contract:

```bash
cd backend && uv run python -m script.export_openapi
cd ../frontend && bun run api:generate
```

To check that the committed client matches the backend:

```bash
make api-check
```

It re-exports the schema, regenerates the client, and fails on any diff. This
keeps the convenience of a committed client without letting it drift silently.
The schema currently declares 79 paths. Operation IDs are stable unless a
contract change is intentional. The committed client includes the account,
password-change, and root-only account operations; the folder, move, and copy
operations; the page-context request/detail/entry-kind contracts; agent runtime
settings; conversation compact/clear operations; saved-question CRUD/ask
operations; and the async ingest-job and ingestion-settings operations. The
library board, settings panel, question book, account directory, and chat desk
call the generated hooks directly.

### Load a real corpus

The Wikipedia loader exercises the same ingestion path as the UI:

```bash
cd backend
uv run python -m script.ingest_wikipedia \
  --lang en --titles Automobile Dendrochronology \
  --prefix /wikipedia/en
```

Ask a question across the imported corpus from the agent desk at `/chat`, or
save it to the question library at `/questions` and run it later.

### Long-document validation

The saved-question flow was also exercised manually against a full-length
Chinese novel. This is a validation example, not a committed fixture or test:

- 《紅樓夢》 (Dream of the Red Chamber) from Project Gutenberg, about 2.66 MB.
- Ingested at 4,000-character chunks with 500-character overlap: 268 chunks.
- Real `deepseek-flash` turns answered questions about Baoyu and Daiyu's
  past-life debt and the 還淚 vow, the stone's descent and 通靈寶玉 in chapter
  one, and the ending where 寶玉 leaves with the monk and the Taoist.
- Answers carried citations such as `[file:27#...]`; no truncation was reported
  at the current tool-result limits.

A separate manual check exercised the durable queue. The job advanced through
`queued`, `parsing`, `chunking`, `embedding` with an `Embedding x / y` count,
`summarizing`, and `ready`; the file did not appear in search until it was
ready. Changed worker values saved in Settings were read by the next worker
loop without a restart, and a changed chunk target affected only subsequent
ingests.

The integration suite remains provider-free and is not extended with this
corpus.

## Development checks

```bash
# Everything at once (offline lint, then tests, then the contract gate)
make lint
make test
make api-check
make audit        # needs network

# Backend
cd backend
uv run ruff check .
uv run mypy app script
uv run lint-imports          # layer and slice-boundary contracts
PYTHONUTF8=1 uv run bandit -r app script -c pyproject.toml
uv run pip-audit
PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/apsor-archive-pytest.log

# Frontend
cd frontend
bun run lint
bun run typecheck
bun run i18n:check
bun run check:boundaries     # workspace import boundaries
bun run test
bun run build
bun audit
```

`make lint` is the architecture and security gate: ruff, mypy, import-linter
contracts that keep routers, services, domain code, and slices in their layers,
bandit, ESLint, TypeScript, i18n key parity, and the frontend workspace-boundary
check. Branches follow Gitflow: `feat/*` and `fix/*` start from `develop` and
merge back through a pull request, and `develop` merges into `main` for release.

The integration suite uses one real PostgreSQL test database
(`apsor_archive_test`) on the same instance, runs sequentially, and resets every
tracked table between tests. The database is built by `alembic upgrade head`,
not `create_all`, so the `apsor_app` role, grants, and RLS policies are present
in every request. Each test exercises the real HTTP surface and database. The multi-user tests cover the root/user lifecycle,
forced password change, one-time temporary passwords, disable/reset session
revocation, root-only accounts and global settings, private archive isolation
across files, folders, memories, summaries, conversations, questions, and
prompts, per-account prompt caps, direct-SQL RLS denial,
`commit_and_reapply` restoring the scoped context after a checkpoint, per-turn
usage accounting and malformed-completion caps, account usage rollups,
impersonation round trips, root-password re-authentication, and root password
rotation revoking impersonation sessions. The agent
test covers runtime settings defaults,
full PUT/reset, validation, the runtime snapshot used by later runs, auto and
manual compaction, clear, page-context reattachment at a boundary, retry,
parallel/sequential tool execution, human save-memory approval (no write before
approval, restart survival, exactly-once approve, reject, orphan/archived
fail-closed recovery), the approval toggle (default waiting path, direct
backend-authorized write when off, and pending rows surviving a toggle change),
the saved-question library, the two read-only web tools including page-mode
traversal and long-line wrapping, and the compressed-summary XML. The provider coverage creates multiple saved rows per
capability, proves the partial unique active index, clears keys without ever
returning plaintext, tests the injected provider probe, and verifies identity
ids are not reused after delete. The prompt coverage creates, lists, updates,
orders by `sort_order`, caps at 20 rows, and deletes frequently used prompts. The
file-library test also uploads an image without a vision provider and verifies
the filename caption, stored original, path listing, and search result; its R2
case exercises the adapter with a fake client and checks missing-object
translation without network access.

The latest migration is `e7b2d5a9c4f1`. The migrations after `agent_config` on
this branch are:

- `f3c8d5a1b7e2` drops the turn-wide tool-result budget;
- `a6e2f9c4d1b8` raises the per-result tool character cap to 100,000;
- `c9f1a2b3d4e5` raises `max_total_tokens` to 100,000 and
  `compaction_threshold_tokens` to 75,000;
- `b7d2e9c4a1f6` creates `saved_question` and its conversation FK/index;
- `e2b7c4d9a6f1` raises the `max_steps` default from 8 to 24 and updates an
  untouched default row;
- `d1e2f3a4b5c6` creates `file_ingest_job` with its status/source/range checks,
  active-path unique index, and file FK;
- `d4b8e6f1a2c7` creates the singleton `ingest_config`, enforces its ranges and
  overlap rule, and seeds row `1`;
- `b3e5c7d9f1a2` adds `context_window_tokens` to `agent_config` with a
  1,000,000 server default and an 8,000–2,000,000 check constraint;
- `c8f2a4b6d9e1` adds the non-null `save_memory_requires_approval` boolean to
  `agent_config` with a `true` server default; existing rows receive `true`;
- `f2b3c4d5e6a7` creates `agent_approval` with its status check,
  conversation/run/entry foreign keys, status indexes, and the partial unique
  pending `(run_id, tool_call_id)` index;
- `8f4b2c6d9e01` drops the retired `media_ngram` and `media_asset` tables. Its
  downgrade recreates the original media schema;
- `c4d8e2f6a1b9` creates the explicit `folder` table, copies current folder rows
  from `tree_node` with their ids, and drops `tree_node`. File leaves are now
  derived from `file.raw_file_path`. The downgrade recreates current folder rows
  and current file leaves;
- `d5e9f3a7b2c1` creates the singleton `system_prompt` table for the
  root-authored first system section;
- `e1a2b3c4d5f6` splits `ai_provider_config` into four capability tables
  (`chat_provider_config`, `embedding_provider_config`,
  `web_search_provider_config`, `web_fetch_provider_config`), copies existing
  chat/embedding rows, and creates the per-table partial unique active indexes;
- `a3f7c9d1e5b2` creates `frequently_used_prompt` and seeds the three
  shortcuts that used to be hard-coded in the chat empty state;
- `b8d2e4f6a1c3` relabels `dendro-hash-384` chunks to `apsor-hash-384` after
  the Apsor Archive rebrand;
- `c9e1f3a5b7d2` replaces the singleton `system_prompt` table with ordered
  `system_prompt_section` rows and copies the existing prompt as the first
  section;
- `f4a1c7d9e2b3` adds `memory.title` (backfilled from content),
  `deprecated_at` / `deprecated_reason`, `builtin_key` on
  `system_prompt_section` for editable built-in overrides, and
  `app_user.display_name` / `bio`. The old “deprecated must have a successor”
  check becomes “successor or direct deprecation timestamp”. The downgrade
  re-adds the old check as `NOT VALID` so direct deprecations keep their rows;
- `b7e2d4f6a8c1` creates `user_profile_card` with ordered title/content rows,
  migrates the existing `app_user.bio` into an `About` card, and drops the
  single bio column;
- `e5c1a9d3b7f2` unifies custom sections and built-in overrides into one
  `system_prompt_section` table. The upgrade materializes the effective built-in
  bodies as ordinary rows after the custom rows, deletes the override rows, and
  drops `builtin_key` and its constraints. All rows are now editable, deletable,
  and reorderable; `reset` replaces the collection with the four seeded
  defaults;
- `b8f4c2d9e6a1` raises the `max_tool_calls_per_turn` default from 6 to 20 and
  promotes an untouched stored default row;
- `e8f1c4d2a7b9` adds `user_id` ownership to every private table,
  composite `(id, user_id)` lineage foreign keys, per-account unique indexes,
  `file.storage_backend` / `file_ingest_job.storage_backend`, the single-root
  partial unique index, and the `role` / `is_active` / `must_change_password`
  account columns. It backfills existing rows to the oldest account, creates the
  non-login `apsor_app` role, revokes `alembic_version` from it, and enables
  forced RLS with owner policies on private tables and read/root-write policies
  on global config tables. Auth tables stay outside RLS;
- `f9c2a7d4e6b1` adds per-run token/API-call counters to
  `agent_run`, per-account rollups to `app_user`, the usage-delta trigger, and
  the nullable `user_session.impersonator_user_id` impersonation marker. It
  backfills historical usage from assistant-entry JSON and requires a
  superuser/BYPASSRLS migration role for the forced-RLS backfill;
- `a4c8e2f6b9d1` removes the `max_total_tokens` column and its check
  constraints, repairs a compaction threshold that is not below its context
  window, and replaces the old threshold rule with
  `compaction_threshold_tokens < context_window_tokens`. The downgrade restores
  a 100,000-token ceiling and raises it when the stored threshold requires it;
- `a1c3e5f7b9d2` raises the compaction threshold range to 1,000,000 tokens.
  The downgrade clamps stored values back to 200,000 before restoring the old
  check constraint;
- `c2f6a8d4e1b3` adds
  `ingest_config.vision_description_language` as a non-null `varchar(80)` with
  an `English` server default and a trimmed-length check. The downgrade drops
  the check and column;
- `f7a3c2d9e1b4` adds the nullable
  `ingest_config.vision_image_prompt` / `vision_document_prompt` templates, the
  `file` prompt fingerprint columns, and `file_ingest_job.source_file_id` with
  its owner-safe composite FK, re-ingest check, active-source unique index, and
  lookup index. It does not seed or backfill prompt/fingerprint values. The
  downgrade removes re-ingest jobs before restoring the old source-kind check;
- `a4c9e2f7b1d6` adds the eight per-account assignment columns and
  their two `ON DELETE SET NULL` endpoint foreign keys, the seven assignment
  check constraints, `chat_provider_config.max_output_tokens`, the widened chat
  provider check that admits `anthropic`, and the four new `agent_config`
  columns. It backfills the lowest active non-`none` chat row and its model into
  any account with no assignment; if no such row exists, every account stays
  unassigned. Accounts created after the migration inherit the same primary
  endpoint and model when one exists; without one they start unassigned. The
  downgrade drops the assignment columns and refuses to restore
  the narrower provider check while an `anthropic` row exists;
- `d8f2a6c4e1b9` drops `agent_config.max_steps` and
  `agent_config.max_tool_calls_per_turn` with their checks and the
  `parallel_within_tool_calls` relation, so a tool-heavy turn keeps running
  until the model answers. The concurrency bound `max_parallel_tools` stays.
  The downgrade restores both columns and raises the restored call cap to at
  least `max_parallel_tools`;
- `c3e7a1f5b9d2` widens the `storage_backend` checks on `file`,
  `file_ingest_job`, and `agent_chat_attachment` to admit `s3` (RustFS, AWS S3,
  MinIO); `rustfs` is only a configuration alias and `r2` stays distinct. The
  downgrade restores the two-value checks and fails while any row still records
  `s3`;
- `c7a3e9f1d5b2` creates the private `file_thumbnail` table:
  one tiny WebP per file version (at most 32 KiB, 512 px), owner-safe composite
  foreign key to `file` with `ON DELETE CASCADE`, forced RLS with an owner
  policy, and `apsor_app` grants. Existing files are filled in by the worker
  backfill. The downgrade drops the table;
- `a7d3c9e1f5b2` creates the private `companion`,
  `companion_frame`, and `companion_preference` tables, each with `user_id`,
  forced owner-only RLS, and `apsor_app` grants. Frames reference their
  companion through an owner-safe composite foreign key and cascade with it; the
  preference row is keyed by `user_id`. The downgrade drops the three tables;
- `b8e4d2f6a1c3` creates the private `companion_story`,
  `companion_lore_fragment`, and `companion_bond` tables with forced owner-only
  RLS and `apsor_app` grants: one account's per-locale copy of a companion's
  persona and lore, its fragments, and the completed-run count that unlocks lore
  tiers. A custom companion's story cascades with the companion. The downgrade
  drops the three tables.
- `c5f1a8d3e7b4` adds `size` (`compact`, `medium`, `full`;
  default `full`) and `opacity_mode` (`opaque`, `translucent`, `auto`; default
  `opaque`) to `companion_preference`, with check constraints and server
  defaults. RLS and grants are unchanged; the downgrade drops both columns.
- `d2b6f4a8c1e9` adds the nullable `scale` float (0 compact to
  1 full) to `companion_preference` for direct on-screen resizing, with a
  range check. NULL means "use `size`"; sending only `scale` derives `size`,
  and sending only `size` clears `scale`. RLS and grants are unchanged; the
  downgrade drops the column.
- `e4c8a2f6b0d3` adds `companion_lore_told` (per account, companion and
  fragment: `told_count`, `offered_at`, `last_told_at`, `source`) and
  `companion_bond.last_story_run` for story-moment pacing. Owner-only RLS.
- `f1a6c3e8b2d4` adds the global, root-editable companion world tables
  (`companion_preset`, `_preset_text`, `_lore_item`, `_lore_item_text`,
  `_canon_entity`, `_world_doc`, `_world_doc_revision`, `_config`,
  `_prompt_template`, `_seed_state`), seeded from `lore/` with
  `seed_hash`/`admin_modified`/`upstream_seed_hash` so root edits survive
  upgrades. Read-all, root-write.
- `a2d7e4f9c3b5` adds the `app.admin_scope = 'companion'` policies (root may
  read and write companion story rows only, never the archive), the
  admin-managed per-account tables (`companion_account_policy`,
  `_user_config`, `_admin_story_override`, `_admin_lore_override`; the account
  can read but not write them), new bond columns, `companion_lore_fragment.refs`,
  and the append-only `companion_admin_access_log`.
- `b3e8f5a1d6c7` adds `companion_generated_story` and `companion_story_job`
  for worker-written life stories.
- `e7b2d5a9c4f1` (current head) adds `chunk.embedding_failures`, a partial
  pending-embedding index, and converts JSON `null` embeddings to SQL NULL so
  the worker can backfill vectors after a provider or allowance outage.

Earlier, `e7a1c4b9d2f6` created the singleton `agent_config` table and seeded
row `1`. The integration suite runs the migration chain on a disposable
PostgreSQL database, so it verifies the role, grants, and RLS policies; Alembic
downgrade is still validated separately against a development database.

## Project layout

The Python package is `apsor-archive-backend` (CLI `apsor-archive`) and the
client package is `apsor-archive-frontend`.

```text
backend/
  app/
    main.py                     API assembly, lifespan, gzip, SPA mount
    worker.py                   dedicated durable-ingestion process
    bootstrap.py                shared process setup and background loops
    shared/                     error registry and list envelope
    infrastructure/             config, database, cache, embeddings, AI, web, files
    module/knowledge/
      domain/                   chunking, n-grams, BM25 terms, timeline, summary
      model/                    SQLAlchemy models incl. ingest jobs/config
      repository/               persistence, retrieval, and job-queue queries
      service/                  orchestration, indexing, ingest jobs/settings
      router/                   HTTP adapters incl. file intake and settings
      schema/                   Pydantic contracts
      exception/                stable error codes
    module/auth/                accounts, roles, sessions, profile cards
    module/agent/               transcript, runtime settings, compaction, tools,
                                saved questions, SSE
    module/prompt/              editable frequently used chat prompts
    module/web_research/        web search/fetch service, URL safety, cache
  alembic/                      migrations
  tests/                        integration tests (PostgreSQL, offline fakes)
frontend/
  src/app/
    component/                  shared archive UI
    generated-apis-types/       committed Orval client
    auth/                       setup/login gate, forced password change
    accounts/                   root-only account directory
    agent/                      page capture, trace, and inspector panels
    chat/                       reading room, retry, context actions
    questions/                  saved-question Q&A library
    settings/                   role-filtered provider and runtime panels
    library/                    files, media gallery, memories, preview modal, intake
    dashboard/ search/ timeline/ about/ ...
  src/apis/fetch-client.ts      the only JSON mutator
  src/apis/agent-stream.ts      SSE transport for agent turns
  src/lib/                      formatting and safe highlighting
  src/styles/                   paper / night archive tokens
  scripts/                      PDF.js asset copy, i18n parity, workspace boundaries
  dist/                         generated build output, gitignored
docker-compose.yml              production stack: Caddy + Cloudflare Tunnel
docker-compose.dev.yml          local dependencies
docs/cloudflare-tunnel.md       tunnel deployment, backup, and security guide
docker/caddy/                   non-root reverse proxy
```
