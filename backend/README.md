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
- `DENDRO_STATIC_DIR` defaults to the repository's `frontend/dist`
- `DENDRO_TIMEZONE=Asia/Taipei`

Every setting is prefixed with `DENDRO_`. The app also reads `.env`,
`.secrets/deepseek.env`, and `.secrets/openai.env` for local development
(using both the current directory and its parent).

## AI

Set `DENDRO_DEEPSEEK_API_KEY`, or configure a chat provider in Settings, to
enable `POST /api/v1/ask`, AI-generated memory summaries, and the persistent
archive agent. The default model is `deepseek-flash`. Without a configured
provider:

- summaries use the deterministic extractive fallback (`generator=extractive`);
- `/api/v1/ask` returns `503 ai_not_configured`;
- agent messages return `503 agent_not_configured`.

## Agent conversations

`/api/v1/agent` is a persistent, Pi-shaped multi-turn archive agent. The schema
is deliberately not a mutable chat log:

- `agent_conversation` stores transcript metadata, provider/model identity, and
  `provider_session_id`.
- `agent_entry` stores immutable entries. `model` is exactly the provider
  payload; `data` is UI/diagnostics and is never sent to the provider. Supported
  kinds are `pi.user`, `pi.assistant`, `pi.tool-result`, `pi.page-context`,
  `pi.system`, `pi.reset`, `pi.compaction`, and `ui.notice`.
- `agent_run` stores one submission's operational state. `agent_commit_seq`
  assigns one sequence value to every entry written in the same transaction.
- `agent_config` is the singleton runtime-limit row (`id=1`). It stores the
  twelve validated limits used by the loop; provider/model identity stays in
  the AI settings table.

Conversation creation appends one frozen `pi.system` entry with ordered prompt
sections, the complete tool snapshot, and prompt/tools versions. The context
builder replays entries in ascending id order, applies the newest `edits`
(`omit`/`replace`), honors `head_entry_id`, moves tool results directly after
their assistant call in call order, synthesizes missing results, drops orphan
results, and excludes assistant entries marked `error`/`aborted`/`cancelled`.
Tool results are XML-wrapped data; tool validation failures are structured
results rather than HTTP 500s.

`agent_run.status` declares `running`, `waiting`, `completed`, `failed`, and
`cancelled`, but only the non-waiting states are emitted today. The unique index
for an active run covers `status = 'running'`; `waiting` is reserved for a future
resume/approval flow.

Endpoints (all require the session cookie):

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/agent/conversations` | Create conversation + system entry |
| `GET` | `/api/v1/agent/conversations` | List active/archived, newest activity first |
| `GET` | `/api/v1/agent/conversations/{conversation_id}` | Metadata + first entry page |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/entries?after_id=&limit=` | Ascending entry page |
| `PATCH` | `/api/v1/agent/conversations/{conversation_id}` | Rename, archive, or restore |
| `DELETE` | `/api/v1/agent/conversations/{conversation_id}` | Soft delete |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/compact` | Append a manual compaction boundary |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/clear` | Append a reset boundary |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/messages` | Append user entry + run |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/retry` | Retry latest failed/cancelled run |
| `GET` | `/api/v1/agent/tools` | Current tool catalog + versions |
| `GET` | `/api/v1/agent/settings` | Effective runtime config + defaults + source |
| `PUT` | `/api/v1/agent/settings` | Replace all twelve runtime fields |
| `POST` | `/api/v1/agent/settings/reset` | Persist the built-in defaults |

`POST /api/v1/agent/conversations/{conversation_id}/messages` takes
`{content, request_id?, page_context?}`; `POST .../retry` takes
`{request_id?}`. Retry creates a new run for the same user entry, so it never
duplicates the user message. The latest run must be `failed` or `cancelled`.

Messages and retry stream `text/event-stream` by default; send
`Accept: application/json` for the completed turn. Event names are `run_start`,
`message_start`, `message_delta`, `message_end`, `tool_start`, `tool_end`,
`run_end`, and `error`. `message_start` carries `entry_id=null`; the assistant
entry id arrives at `message_end`, and deltas are never persisted.
`tool_start` and `tool_end` include `parallel`, `batch_size`, and
`parallel_index` for the current batch. SSE headers disable proxy buffering
(`Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`) and
Starlette's GZip middleware excludes `text/event-stream`.

The runtime defaults cap a turn at 8 model steps, 6 tool calls, 6 parallel
tools, 64,000 total tokens, 12,000 characters per tool result, and 24,000
tool-result characters overall. All of these come from the immutable
`agent_config` snapshot, not from module constants. The loop uses
`app.state.db.session_factory()` for appends and a short-lived session for each
tool call, so the stream does not hold the request session.

### Runtime settings

`agent_config` is a singleton row (`id=1`). `GET /api/v1/agent/settings`,
`PUT /api/v1/agent/settings`, and `POST /api/v1/agent/settings/reset` are thin
adapters over `AgentSettingsService` with operation ids `getAgentSettings`,
`updateAgentSettings`, and `resetAgentSettings`. The read body is:

```json
{
  "config": {"max_total_tokens": 64000, "...": "..."},
  "defaults": {"max_total_tokens": 64000, "...": "..."},
  "source": "database",
  "updated_at": "2026-10-19T15:00:00Z"
}
```

`source` is `default` only when the service had to create or repair the row from
the built-in defaults; a normal read of the stored row returns `database`.
`PUT` requires all twelve fields and uses `extra=forbid`, so it is a full
replacement rather than a patch.

| Field | Default | Constraint |
|---|---|---|
| `max_total_tokens` | 64,000 | 8,000–200,000; cumulative across model steps |
| `compaction_threshold_tokens` | 48,000 | 1,000–200,000; `< max_total_tokens` |
| `max_steps` | 8 | 1–32 |
| `max_tool_calls_per_turn` | 6 | 1–24 |
| `max_parallel_tools` | 6 | 1–24; `<= max_tool_calls_per_turn` |
| `max_tool_result_chars` | 12,000 | 1,000–100,000; `<= total` |
| `max_total_tool_result_chars` | 24,000 | 1,000–200,000 |
| `max_page_context_chars` | 6,000 | 500–50,000 |
| `max_compaction_summary_chars` | 6,000 | 1,000–20,000 |
| `max_compaction_last_user_chars` | 4,000 | 500–10,000 |
| `auto_compaction_enabled` | `true` | boolean |
| `parallel_tools_enabled` | `true` | boolean |

Pydantic validates the request and `AgentRuntimeConfig` repeats the same
cross-field checks; PostgreSQL check constraints enforce the ranges and all
three cross-field rules. The global validation handler maps request validation
failures to `400 invalid_request`, not 422.

`get_agent_runtime_config` loads one snapshot in a short-lived session and
returns a frozen dataclass. The dependency runs before an SSE response starts;
an already active run keeps its snapshot, while a later run reads the current
row. Provider and model still come from `/api/v1/settings/ai`.

### Compaction and clearing

Auto compaction runs before a new user turn when
`auto_compaction_enabled` is true, the active context has at least one user
entry, and the estimated context exceeds `compaction_threshold_tokens`.
`estimate_context_tokens` uses a conservative character estimate and the latest
valid assistant usage, whichever is larger.

The service appends one `pi.compaction` entry with `head_entry_id` set to its own
id. Its provider message is a user-role envelope:

```xml
<compaction><last_user_input>...</last_user_input><summary>...</summary></compaction>
```

The summary and last-user text are clipped by the active snapshot's
`max_compaction_summary_chars` and `max_compaction_last_user_chars`. The same
transaction writes compaction → page context (if the page is reattached) → user,
all with one `commit_seq` and `by_run_id`. Older entries remain immutable but
fall outside the new active context.

`POST .../compact` builds the same deterministic summary manually (`reason:
"manual"`, `auto: false`) without a provider call. `POST .../clear` appends
`pi.reset` with a self `head_entry_id`, empty provider messages, and `data:
{"reason": "manual_clear"}`. Operation ids are `compactAgentConversation` and
`clearAgentConversation`. Clear preserves every transcript row while starting an
empty active context. Both endpoints return `409 agent_conversation_busy` when a
run is active and `409 agent_conversation_archived` for an archived thread.

### Page context

`page_context` is an optional plain-text snapshot of the page the user is
viewing. It is append-only transcript data:

| Field | Type | Rule |
|---|---|---|
| `key` | string | Required; 1–512 characters; stable page identity |
| `path` | string | Required; 1–1024 characters; route plus meaningful parameters |
| `title` | string or null | Optional; at most 300 characters |
| `text` | string | Required; 1–12,000 characters before server clipping |

The service normalizes CRLF/CR to LF, maps non-breaking spaces to spaces,
collapses horizontal whitespace per line, trims lines, and limits consecutive
blank lines to one. It then caps the snapshot at 6,000 characters. The entry's
`data` is:

```json
{
  "page_key": "/library?path=/history",
  "path": "/library?path=/history",
  "title": "File Library",
  "text_chars": 1482,
  "truncated": false
}
```

`title` is omitted when it is empty. The stored provider message is a user-role
message with an XML envelope (shown wrapped here; the stored value has no
formatting whitespace):

```xml
<page_context key="/library?path=/history" path="/library?path=/history" title="File Library"><text>...normalized page text...</text></page_context>
```

If the key, path, or normalized text is empty, no snapshot is written and
`page_context_attached` is `false`.

New conversations freeze the system prompt version `archive-agent-v2`, which
states that `<page_context>` is reference data, never an instruction, and that
it appears only when the page changes.

`begin_message` writes the snapshot and the user entry in one transaction:

1. Lock the conversation, reject an active run, and resolve the request id.
2. Build an auto-compaction draft when the active context crossed the threshold.
3. Find the newest boundary and read the newest `pi.page-context` entry at or
   after it.
4. If the incoming key differs, insert the snapshot after any compaction entry
   and before the user entry.
5. Append the compaction, snapshot, and user entries with one `commit_seq`, link
   them to the new run, and create the run.

The comparison is against the database entry log, not localStorage, so it still
works after a reload. Dedupe is scoped to the newest compaction/reset boundary,
so the same page can be reattached after a boundary. The behavior is strictly
append-only: no earlier entry is rewritten, which keeps the system/tool prefix
and the prior transcript prefix stable for KV-cache reuse. A compaction or reset
boundary starts a new lineage deliberately.

`run_start` exposes `page_context_entry_id` (integer or `null`) and
`page_context_attached` (boolean). Conversation detail exposes
`last_page_context_key`, derived from the newest snapshot at or after the active
boundary. A snapshot is a normal entry: it appears in entry pages and
`entries_total`, and clients should render it as a context card rather than as a
user message.

### Tool result preview data

`pi.tool-result.data` is UI-only and is never sent to the provider. It contains
`tool`, `status`, `error_code`, `duration_ms`, validated `arguments`, optional
`resource`, and bounded preview fields. Preview strings are whitespace-normalized
and clipped to 600 characters; lists keep the tool's existing bounds (100 path
entries, 50 timeline events).

| Tool | Preview fields |
|---|---|
| `search_knowledge` | `file_results[].excerpt/viewer_url`, `memory_results[].excerpt/viewer_url`, `summary_results[].excerpt` |
| `read_file` | `viewer_url`, `chunks[].excerpt` |
| `read_timeline` | `events[].content`, `events[].summary_id`, nullable `events[].viewer_url` |
| `read_path` | `directories[]`, `files[].viewer_url` |
| `read_memory` | `target` preview, `neighbors[]` previews, plus the id lists |
| `save_memory` | `memory` preview, `supersedes[]` |
| `search_media` | `excerpt`, `width`, `height`, `tags[]`, `viewer_url` |
| `get_media` | `caption`, `summary`, `ocr_text`, `viewer_url` |
| `present_resource` | `resource` descriptor |

The live `tool_end` SSE event carries `entry_id`, `tool_call_id`, `name`,
`status`, optional `resource`, the UI-only `data`, `duration_ms`, and
`error_code` fields, plus `parallel`, `batch_size`, and `parallel_index`. The
matching `tool_start` carries the same batch fields. `data` mirrors the persisted
`pi.tool-result` payload, so a live inspector can render the same excerpts,
dimensions, tags, memory previews, and viewer URLs without waiting for a
transcript refetch. Provider-facing tool content remains the separate XML
payload in `model`.

Tool names: `search_knowledge`, `read_file`, `read_timeline`, `read_path`,
`read_memory`, `save_memory`, `search_media`, `get_media`, `present_resource`.
`save_memory` is a write action and requires `user_confirmed=true`; the system
prompt also requires an explicit user request and confirmed wording. The flag is
model-supplied, and there is no separate approval dialog in the frontend yet.
The expanded inspector renders the resulting receipt; it does not approve the
write.
`present_resource` returns `/viewer/file/{id}?chunk={n}`, `/viewer/media/{id}`,
or `/viewer/memory/{id}` and does not fetch or open the resource.

For tests, inject `FakeChatGenerator` from
`app/module/agent/test/fake_chat_generator.py` through
`app.state.agent_chat_generator` or by overriding `get_agent_chat_generator`.
No external provider call is made.

## Folder and file organization

Three session-protected endpoints back the library board:

| Method | Path | Body | Success |
|---|---|---|---|
| `POST` | `/api/v1/folders` | `{path}` | `201` with `{path, name, depth}` |
| `POST` | `/api/v1/files/{file_id}/move` | `{path}` | `200` with the file |
| `POST` | `/api/v1/files/{file_id}/copy` | `{path}` | `201` with the new file |

`path` is at most 1,024 characters. Empty values reach the service so they
produce the stable `invalid_path` domain error rather than a generic schema
error.

### Create folder

`create_folder` normalizes a directory path, rejects `/`, and creates every
missing ancestor. Repeating the request, including with a trailing slash, returns
the same folder and `201`. A path occupied by a file, or by a non-folder node,
returns `409 tree_path_conflict`. The archive cache version is bumped only when
a new folder is created.

### Move

`move_file` requires a current, non-deleted file id. It normalizes the target,
requires the same extension, and rejects a target occupied by any current tree
node or file with `409 tree_path_conflict`. Moving to the current path is an
idempotent `200`.

A move updates `file.raw_file_path` and `file.file_name` in place. It reuses the
existing tree node when it is the file's current node and creates one otherwise.
The file id, version, `is_current`, chunks, embeddings, storage key, original
bytes, and history links are unchanged. The path/tree cache version is bumped.
Search, timeline, citations, and viewer links keep working because the id does
not change.

### Copy

`copy_file` requires a current, non-deleted source and a free target path with
the same extension. It creates a new current file record at version 1 with a new
id:

- The stored original is copied to a new storage key when the source has one.
  Text-only records are reconstructed from their current chunks by removing the
  known overlap, then re-chunked.
- Chunks and embeddings are rebuilt, not shared.
- `ai_summary`, `ai_tags`, `document_type`, and `extraction_method` are copied.
- The new record's `created_at` and `updated_at` are the copy time; it does not
  inherit the source timestamp.
- Source history and supersession links are not copied.

Both records remain current and searchable after a copy. Failures while
persisting the new bytes delete the newly written storage object.

### Errors

| Error code | Status | Cause |
|---|---|---|
| `invalid_path` | 422 | Empty path, `/`, traversal, or changed extension |
| `tree_path_conflict` | 409 | Target is occupied by another current node or file |
| `file_not_found` | 404 | File id is missing, deleted, or not current |
| `unsupported_file_type` | 422 | Upload extension is outside the allowlist |
| `file_too_large` | 413 | Upload exceeds 10 MB, or text creation exceeds 2 MB |
| `empty_content` | 422 | Text-only copy has no reconstructable content |

## Viewer content

`GET /api/v1/files/{file_id}/content` returns the stored original inline. It is
distinct from `/download`:

- `Content-Disposition: inline`, stored MIME, `X-Content-Type-Options: nosniff`;
- restrictive CSP (`sandbox` for non-PDF, `frame-ancestors 'self'` for PDF);
- `Accept-Ranges: bytes`, single-range `206`/`416`, `ETag` and `304`;
- `Cache-Control: private, max-age=0, must-revalidate`;
- 404 `file_content_unavailable` when a text-only record has no original.

The `FileSchema.has_original` flag tells the UI whether to show **Open original**
and **Download**. Text-only records skip the `/content` probe entirely and read
indexed chunks; if they have no chunks either, the viewer shows a readable error.
If a record claims an original but `/content` returns
`file_content_unavailable`, the sheet still falls back to chunks.

The frontend uses `/viewer/file/:fileId`, `/viewer/media/:mediaId`, and
`/viewer/memory/:memoryId`; PDF/DOCX/image engines are lazy-loaded and never execute
uploaded scripts. `/api/v1/media/{media_id}/content` remains inline for media
images.
PDF.js CMaps and standard fonts are copied into `frontend/public/pdfjs` by
`frontend/scripts/copy-pdfjs-assets.mjs`, then emitted into
`frontend/dist/pdfjs` by Vite. The Docker image copies the committed `dist`, so
those generated assets must be committed with the build.

## Account and sessions

The first visit creates the single owner account through
`POST /api/v1/auth/setup`. Passwords are hashed with Argon2; sessions are opaque
cookies whose SHA-256 hash is stored in `user_session`. The cookie is HttpOnly and
SameSite=Lax; set `DENDRO_COOKIE_SECURE=true` behind HTTPS. Every knowledge,
media, settings, and agent endpoint requires the session; `/api/v1/health`,
`/health`, `/api/v1/auth/*`, `/docs`, `/redoc`, `/openapi.json`, and the SPA
shell are public. There is no password recovery, by design.

## Database

Alembic owns the schema. The initial migration creates `pg_trgm` and six archive
tables: `file`, `tree_node`, `chunk`, `chunk_ngram`, `memory`, and
`memory_summary` (plus Alembic's own `alembic_version`). Later migrations add
provider settings, standalone media, document analysis fields, account/session
auth (`app_user`,
`user_session`), and the three agent tables (`agent_conversation`,
`agent_entry`, `agent_run`) plus the `agent_commit_seq` sequence. The agent
migration is `a7c41e9d2b60`, after `f3cd26ca9f67`. The page-context migration
`c4f1a9e2b7d3` follows it and updates the entry `kind` and `model` check
constraints to include `pi.page-context`; it does not add a table or column.
The runtime-config migration `e7a1c4b9d2f6` follows `c4f1a9e2b7d3`, creates the
singleton `agent_config` table with all range and cross-field check constraints,
and seeds row `id=1` with the defaults.

The page-context migration names both existing constraints through `op.f(...)`.
That matters on a real database: the constraint names must be the exact
Alembic/PostgreSQL identifiers that `a7c41e9d2b60` created. The application test
suite builds tables from SQLAlchemy metadata (`Base.metadata.create_all`), so it
does not execute Alembic and would not catch a bad constraint name by itself.
Validate migration upgrade/downgrade separately against the development
database.

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
    router/                HTTP adapters (including folder_router.py)
    schema/                Pydantic request/response contracts
    exception/             stable domain errors
    dependencies.py        composition root
  module/media/            standalone image library and visual search
  module/agent/
    domain/                replay builder, compaction, runtime config, envelopes
    model/                 conversation, immutable entry, run, agent_config
    protocol/              chat, repository, settings-repository protocols
    repository/            transaction, commit-sequence, config persistence
    service/               agent loop, settings, context projection, tool registry
    router/                conversation, compact/clear, settings, tools
    schema/                request/response and settings contracts
    exception/             stable agent errors
    test/                  FakeChatGenerator (no collected tests)
    dependencies.py        composition root + snapshot + fake-provider seam
```

The agent uses `app.state.db.session_factory()` rather than the request session,
so an SSE response never holds a request-scoped session. Runtime settings use a
separate short-lived session in `get_agent_runtime_config`, which returns one
frozen `AgentRuntimeConfig` per request. The test seam is
`app.state.agent_chat_generator` or an override of
`get_agent_chat_generator`.

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
as errors. There are exactly ten collected tests:

1. `tests/test_agent.py::test_agent_entry_log_tool_loop_and_cache_usage`
2. `tests/test_errors.py::test_validation_and_error_envelope`
3. `tests/test_file_library.py::test_file_ingest_path_read_and_soft_delete`
4. `tests/test_memories.py::test_save_memory_supersede_and_trace`
5. `tests/test_memories.py::test_read_memory_neighbors`
6. `tests/test_search.py::test_hybrid_search_and_union_query`
7. `tests/test_summaries.py::test_summary_fallback_and_search`
8. `tests/test_system.py::test_health_gzip_and_cache_invalidation`
9. `tests/test_timeline.py::test_timeline_sparse_sampling`
10. `tests/test_versions.py::test_tree_history_and_versioning`

The agent test injects a deterministic `FakeChatGenerator` by assigning
`client.app.state.agent_chat_generator`; no DeepSeek or OpenAI request is made.
It also covers runtime settings defaults, full PUT and reset, validation
failures (`400 invalid_request`), runtime snapshot handling for later runs, auto
and manual compaction, clear, the page-context boundary and same-page
reattachment, retry, and parallel versus sequential tool execution. The file library test
covers idempotent folder creation, in-place moves, independent copies, extension
checks, and path conflicts. The former two search tests are merged into
`test_hybrid_search_and_union_query`, which is what keeps the suite at ten
collected functions.

The suite does not execute migrations; upgrade and downgrade are separate
checks against the development database. Runtime settings and compaction are
validated by Pydantic, the frozen `AgentRuntimeConfig`, and PostgreSQL check
constraints.
