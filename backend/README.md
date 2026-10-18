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
  kinds are `pi.user`, `pi.assistant`, `pi.tool-result`, `pi.system`, `pi.reset`,
  `pi.compaction`, and `ui.notice`.
- `agent_run` stores one submission's operational state. `agent_commit_seq`
  assigns one sequence value to every entry written in the same transaction.

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
| `POST` | `/api/v1/agent/conversations/{conversation_id}/messages` | Append user entry + run |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/retry` | Retry latest failed/cancelled run |
| `GET` | `/api/v1/agent/tools` | Current tool catalog + versions |

`POST /api/v1/agent/conversations/{conversation_id}/messages` takes
`{content, request_id?}`; `POST .../retry` takes
`{request_id?}`. Retry creates a new run for the same user entry, so it never
duplicates the user message. The latest run must be `failed` or `cancelled`.

Messages and retry stream `text/event-stream` by default; send
`Accept: application/json` for the completed turn. Event names are `run_start`,
`message_start`, `message_delta`, `message_end`, `tool_start`, `tool_end`,
`run_end`, and `error`. `message_start` carries `entry_id=null`; the assistant
entry id arrives at `message_end`, and deltas are never persisted. SSE headers
disable proxy buffering (`Cache-Control: no-cache, no-transform`,
`X-Accel-Buffering: no`) and Starlette's GZip middleware excludes
`text/event-stream`. The loop caps at 8 model steps, 6 tool calls per user turn,
24k tokens, and 12k characters per tool result (24k total). It uses
`app.state.db.session_factory()` for appends and a short-lived session for each
tool call, so the stream does not hold the request session.

Tool names: `search_knowledge`, `read_file`, `read_timeline`, `read_path`,
`read_memory`, `save_memory`, `search_media`, `get_media`, `present_resource`.
`save_memory` is a write action and requires `user_confirmed=true`; the system
prompt also requires an explicit user request and confirmed wording. The flag is
model-supplied, and there is no separate approval dialog in the frontend yet.
`present_resource` returns `/viewer/file/{id}?chunk={n}`, `/viewer/media/{id}`,
or `/viewer/memory/{id}` and does not fetch or open the resource.

For tests, inject `FakeChatGenerator` from
`app/module/agent/test/fake_chat_generator.py` through
`app.state.agent_chat_generator` or by overriding `get_agent_chat_generator`.
No external provider call is made.

## Viewer content

`GET /api/v1/files/{file_id}/content` returns the stored original inline. It is
distinct from `/download`:

- `Content-Disposition: inline`, stored MIME, `X-Content-Type-Options: nosniff`;
- restrictive CSP (`sandbox` for non-PDF, `frame-ancestors 'self'` for PDF);
- `Accept-Ranges: bytes`, single-range `206`/`416`, `ETag` and `304`;
- `Cache-Control: private, max-age=0, must-revalidate`;
- 404 `file_content_unavailable` when a text-only record has no original.

The `FileSchema.has_original` flag tells the UI whether to show **Open original**
and **Download**. Text-only records fall back to indexed chunks; if they have no
chunks either, the viewer shows a readable error instead of requesting `/content`.

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
migration is `a7c41e9d2b60`, after `f3cd26ca9f67`.

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
  module/media/            standalone image library and visual search
  module/agent/
    domain/                replay/context builder, tool args, XML helpers
    model/                 conversation, immutable entry, run
    protocol/              chat-generator, repository, and tool-service protocols
    repository/            transaction + commit-sequence repository
    service/               agent loop, context projection, tool registry
    router/                conversation, message/retry, tools
    schema/                request/response contracts
    exception/             stable agent errors
    test/                  FakeChatGenerator (no collected tests)
    dependencies.py        composition root + fake-provider seam
```

The agent uses `app.state.db.session_factory()` rather than the request session,
so an SSE response never holds a request-scoped session. The test seam is
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
The former two search tests are merged into `test_hybrid_search_and_union_query`,
which is what keeps the suite at ten.
