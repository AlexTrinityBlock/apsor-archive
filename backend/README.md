# Apsor Archive Backend

FastAPI service for the Apsor Archive knowledge and memory archive.

## Run

```bash
uv sync
uv run alembic upgrade head
uv run apsor-archive --host 127.0.0.1 --port 8000 --reload
```

The API expects PostgreSQL and Valkey. The repository root has
`docker-compose.dev.yml` for both:

```bash
docker compose -f ../docker-compose.dev.yml up -d --wait
```

Default settings:

- `APSOR_DATABASE_URL=postgresql+psycopg://apsor:apsor@127.0.0.1:55432/apsor_archive`
- `APSOR_CACHE_URL=redis://127.0.0.1:56379/0`
- `APSOR_DATA_DIR=backend/data`
- `APSOR_STATIC_DIR` defaults to the repository's `frontend/dist`
- `APSOR_TIMEZONE=Asia/Taipei`

Every setting is prefixed with `APSOR_`. The app also reads `.env`,
`.secrets/deepseek.env`, and `.secrets/openai.env` for local development
(using both the current directory and its parent).

## AI

Set `APSOR_DEEPSEEK_API_KEY`, or configure a chat provider in Settings, to
enable AI-generated memory summaries and the persistent archive agent. The
default model is `deepseek-flash`. Without a configured provider:

- summaries use the deterministic extractive fallback (`generator=extractive`);
- image uploads use a filename-derived caption and metadata;
- agent messages return `503 agent_not_configured`.

## File ingestion

Uploads and direct text can be queued as durable `file_ingest_job` rows. The
synchronous `POST /api/v1/files` and `POST /api/v1/files/text` endpoints remain
for clients that want a fully indexed file in the response. The async routes
store the payload and return `202` with an `IngestJobSchema`:

| Method | Path | Operation |
|---|---|---|
| `POST` | `/api/v1/files/async` | `uploadFileAsync` |
| `POST` | `/api/v1/files/text/async` | `createTextFileAsync` |
| `GET` | `/api/v1/files/ingest-jobs?limit=&offset=` | `listIngestJobs` |
| `GET` | `/api/v1/files/ingest-jobs/{id}` | `getIngestJob` |
| `POST` | `/api/v1/files/ingest-jobs/{id}/retry` | `retryIngestJob` |

The list returns `{total_results, jobs}`, newest first. `limit` is 1–100
(default 20) and `offset` starts at 0. Retry accepts only a failed job whose
attempt budget is not exhausted and returns it to `queued` with `202`.
Missing jobs are `404 ingest_job_not_found`; a path already held by an active
job is `409 ingest_job_conflict`; an ineligible retry is
`409 ingest_job_not_retryable`.

A job reports its durable stage and percentage:

| Status | `progress_pct` | Meaning |
|---|---|---|
| `queued` | 0 | Payload stored; waiting for a worker |
| `parsing` | 5 | Reading and extracting text |
| `chunking` | 15–20 | Splitting text; `chunks_total` may be set |
| `embedding` | 25–90 | Embedding chunks; `chunks_embedded` advances |
| `summarizing` | 95 | Publishing the staged file |
| `ready` | 100 | File and chunks are current and searchable |
| `failed` | — | `error_code` and bounded `error_detail` are set |

`chunks_total` and `chunks_embedded` let a client show `Embedding x / y`.

### Worker lifecycle

One worker process drains the queue. It polls the database every
`poll_seconds` (one second by default) while idle and claims the oldest queued
job with `SELECT ... FOR UPDATE SKIP LOCKED`. Parsing and chunking use a shared
`ThreadPoolExecutor` with two extraction threads, and the worker holds at most
two in-flight jobs. Embedding is async with a global concurrency of six and
batched progress updates; it does not consume extraction threads.

The worker writes a staged file and chunks, ensures its folder chain, embeds,
then
publishes them only after embedding and summary complete. A failed job discards
its staged rows and clears `file_id`, so an unfinished path never appears as a
partial current file or chunk set. On startup, jobs whose heartbeat is older
than the stale window (300 seconds by default) are requeued after their staged
rows are removed; a job over its attempt limit becomes a terminal
`ingest_worker_lost` failure. Embedding retries are bounded by the configured
attempt count and backoff.

The FastAPI lifespan starts one in-process worker by default. For production,
run a dedicated process so parsing and embedding cannot starve request
handlers:

```bash
uv run apsor-archive worker
# or
uv run python -m app.worker
# process at most one queued job, then exit
uv run python -m app.worker --once
```

Both shapes use the same queue and leases. Multiple API replicas should disable
the lifespan worker (`APSOR_INGEST_WORKER_ENABLED=false`) and run one or more
dedicated workers.

### Runtime settings

`ingest_config` is a singleton row (`id=1`). The worker reads a fresh database
snapshot at the start of each loop and each claimed job, so a saved change
applies to the next claim without a restart; a job already running keeps the
snapshot it started with.

| Method | Path | Operation |
|---|---|---|
| `GET` | `/api/v1/settings/ingest` | `getIngestSettings` |
| `PUT` | `/api/v1/settings/ingest` | `updateIngestSettings` |
| `POST` | `/api/v1/settings/ingest/reset` | `resetIngestSettings` |

The read body is `{config, defaults, source, updated_at}`. `source` is
`default` only when the service created or repaired the row; a stored row
returns `database`. `PUT` requires all six fields and uses `extra=forbid`, so it
is a full replacement.

| Field | Default | Constraint |
|---|---|---|
| `poll_seconds` | 1.0 | 0.25–30 |
| `extract_workers` | 2 | 1–8 |
| `max_inflight_jobs` | 2 | 1–4 |
| `embedding_concurrency` | 6 | 1–32 |
| `chunk_target_chars` | 4,000 | 1,000–20,000 |
| `chunk_overlap_chars` | 500 | 0–5,000; `< chunk_target_chars` |

Environment values seed a fresh installation and remain the fallback when the
row is absent. Changing chunk sizes applies only to future ingests; existing
files keep their current boundaries until they are re-ingested. Pydantic,
`IngestRuntimeConfig`, and matching PostgreSQL check constraints enforce the
ranges and the overlap rule; request validation failures map to
`400 invalid_request`.

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
- `agent_approval` stores a pending human decision for a confirmation-required
  tool call: validated arguments, safe preview, and the loop snapshot used to
  resume the waiting run.
- `agent_config` is the singleton runtime-limit row (`id=1`). It stores the
  eleven validated limits used by the loop; provider/model identity stays in
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
`cancelled`. A confirmation-required tool call moves the run to `waiting` and
creates an `agent_approval` row; the run survives an API restart while that row
is pending. The unique index for an active run covers `status = 'running'`;
the service enforces one active (`running`/`waiting`) run per conversation.

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
| `POST` | `/api/v1/agent/conversations/{conversation_id}/fork` | Copy entries through an inclusive cutoff |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/messages` | Append user entry + run |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/retry` | Retry latest failed/cancelled run |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/approvals?status=` | Durable approvals, oldest first (default `pending`) |
| `POST` | `/api/v1/agent/approvals/{approval_id}/approve` | Execute once, append result, resume |
| `POST` | `/api/v1/agent/approvals/{approval_id}/reject` | Append `memory_rejected`, resume without writing |
| `GET` | `/api/v1/agent/tools` | Current tool catalog + versions |
| `GET` | `/api/v1/agent/settings` | Effective runtime config + defaults + source |
| `PUT` | `/api/v1/agent/settings` | Replace all thirteen runtime fields |
| `POST` | `/api/v1/agent/settings/reset` | Persist the built-in defaults |
| `GET` | `/api/v1/agent/questions?limit=&offset=` | List saved questions newest first |
| `POST` | `/api/v1/agent/questions` | Save a question (`201`); question only |
| `PATCH` | `/api/v1/agent/questions/{question_id}` | Edit the question text |
| `DELETE` | `/api/v1/agent/questions/{question_id}` | Delete the saved question (`204`) |
| `POST` | `/api/v1/agent/questions/{question_id}/ask` | Run one agent turn and persist its outcome |
| `GET` | `/api/v1/agent/settings/system-prompt` | List every system prompt section |
| `POST` | `/api/v1/agent/settings/system-prompt` | Create one section (`201`) |
| `PUT` | `/api/v1/agent/settings/system-prompt/order` | Reorder every section |
| `PUT` | `/api/v1/agent/settings/system-prompt/{section_id}` | Replace one section |
| `DELETE` | `/api/v1/agent/settings/system-prompt/{section_id}` | Delete one section (`204`) |
| `POST` | `/api/v1/agent/settings/system-prompt/reset` | Replace every section with the four seeded defaults |

`POST /api/v1/agent/conversations/{conversation_id}/messages` takes
`{content, request_id?, page_context?, client_timezone?,
client_utc_offset_minutes?}`; `POST .../retry` takes `{request_id?}`. Retry
creates a new run for the same user entry, so it never duplicates the user
message. The latest run must be `failed` or `cancelled`.

`POST .../fork` accepts an optional `{at_entry_id?, title?}` body and returns
`201 AgentConversationSchema`. `at_entry_id` is an inclusive cutoff that must
belong to the source conversation and defaults to its latest entry. The fork is
active, has a new `provider_session_id`, records `parent_conversation_id` and
`fork_at_entry_id`, and copies entries through the cutoff in order with new ids
and `commit_seq` values. Copied entries keep their kind/model/data and original
timestamps, get `by_run_id=null`, and have `head_entry_id`/`edits` remapped to
copied ids (out-of-range references are dropped). Runs and approval state are
not copied, and the source transcript is untouched. The default title is
`Fork of {source.title}` clipped to 200 characters. Errors are
`404 agent_conversation_not_found`, `409 agent_conversation_archived`,
`409 agent_conversation_busy`, and `400 agent_fork_entry_invalid` for a cutoff
outside the source.

Messages and retry stream `text/event-stream` by default; send
`Accept: application/json` for the completed turn. Event names are `run_start`,
`message_start`, `message_delta`, `message_end`, `tool_start`, `tool_end`,
`approval_required`, `run_end`, and `error`. `message_start` carries
`entry_id=null`; the assistant entry id arrives at `message_end`, and deltas are
never persisted. `tool_start` and `tool_end` include `parallel`, `batch_size`,
and `parallel_index` for the current batch. `approval_required` carries the
approval id, tool-call id, safe preview, and requested time; the stream then
ends with `run_end {status: "waiting"}`. SSE headers disable proxy buffering
(`Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`) and
Starlette's GZip middleware excludes `text/event-stream`.

Both approval resolution endpoints accept the same JSON fallback. They claim
the row before executing, append the real tool result, and resume at the next
model step. A duplicate, expired, or orphaned resolution returns `409
agent_approval_not_pending`; a non-earliest approval in a multi-call batch
returns `409 agent_approval_out_of_order`.

The runtime defaults cap a turn at 24 model steps, 6 tool calls, 6 parallel
tools, 100,000 total tokens, and 100,000 characters per tool result. Each result
is clipped independently with a visible truncation marker; there is no
turn-wide result budget. `context_window_tokens` (default 1,000,000) records
the provider/model input capacity separately; it is metadata and never triggers
the turn abort or changes compaction. All of these come from the immutable
`agent_config` snapshot, not from module constants. The loop uses
`app.state.db.session_factory()` for appends and a short-lived session for each
tool call, so the stream does not hold the request session.

Startup recovery fails stale `running` runs with `interrupted`. It leaves a
`waiting` run resumable only while a valid pending approval exists; otherwise
the run fails closed with `approval_orphaned` and pending approvals on terminal
runs or archived/deleted conversations are expired.

### Runtime settings

`agent_config` is a singleton row (`id=1`). `GET /api/v1/agent/settings`,
`PUT /api/v1/agent/settings`, and `POST /api/v1/agent/settings/reset` are thin
adapters over `AgentSettingsService` with operation ids `getAgentSettings`,
`updateAgentSettings`, and `resetAgentSettings`. The read body is:

```json
{
  "config": {"max_total_tokens": 100000, "...": "..."},
  "defaults": {"max_total_tokens": 100000, "...": "..."},
  "source": "database",
  "updated_at": "2026-10-19T15:00:00Z"
}
```

`source` is `default` only when the service had to create or repair the row from
the built-in defaults; a normal read of the stored row returns `database`.
`PUT` requires all thirteen fields and uses `extra=forbid`, so it is a full
replacement rather than a patch.

| Field | Default | Constraint |
|---|---|---|
| `max_total_tokens` | 100,000 | 8,000–200,000; cumulative across model steps |
| `compaction_threshold_tokens` | 75,000 | 1,000–200,000; `< max_total_tokens` |
| `context_window_tokens` | 1,000,000 | 8,000–2,000,000; model context metadata, not a turn budget |
| `max_steps` | 24 | 1–32 |
| `max_tool_calls_per_turn` | 6 | 1–24 |
| `max_parallel_tools` | 6 | 1–24; `<= max_tool_calls_per_turn` |
| `max_tool_result_chars` | 100,000 | 1,000–200,000 |
| `max_page_context_chars` | 6,000 | 500–50,000 |
| `max_compaction_summary_chars` | 6,000 | 1,000–20,000 |
| `max_compaction_last_user_chars` | 4,000 | 500–10,000 |
| `auto_compaction_enabled` | `true` | boolean |
| `parallel_tools_enabled` | `true` | boolean |
| `save_memory_requires_approval` | `true` | boolean; waits for user approval before `save_memory` writes |

Pydantic validates the request and `AgentRuntimeConfig` repeats the same
cross-field checks; PostgreSQL check constraints enforce the ranges and all
three cross-field rules. There is deliberately no `context_window_tokens` versus
`max_total_tokens` rule: the context window is provider metadata, while the turn
budget is the cost guard. The global validation handler maps request validation
failures to `400 invalid_request`, not 422.

`get_agent_runtime_config` loads one snapshot in a short-lived session and
returns a frozen dataclass. The dependency runs before an SSE response starts;
an already active run keeps its snapshot, while a later run reads the current
row. Provider and model still come from `/api/v1/settings/providers`.

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

New conversations freeze the current system prompt version
(`archive-agent-v12`), which states that `<page_context>` and `<current_time>`
are reference data, never instructions, and that page context appears only when
the page changes.

### Current time

Every user message may carry the browser clock metadata:

| Field | Type | Rule |
|---|---|---|
| `client_timezone` | string or null | IANA name, 1–64 characters |
| `client_utc_offset_minutes` | integer or null | −840 to 840; current browser offset |

Both are stored on the `pi.user` entry `data`, together with a server-rendered
`time_context` string. The provider request appends that block **after** the user
text. It is written once when the message is created, so every historical user
message keeps its send time and the KV-cache prefix is never rewritten:

```xml
<current_time>
utc: 2026-10-25T00:45:00Z
timezone: Asia/Taipei (UTC+08:00)
timezone_source: browser
local: 2026-10-25T08:45:00+08:00
</current_time>
```

The server owns UTC; a valid IANA zone wins over the numeric offset (so DST is
correct), and a missing or invalid zone falls back to `APSOR_TIMEZONE`. A retry
reuses the original message's stored block. This lets the agent answer "now",
"today", and relative-date questions without inventing a clock.

### System prompt module

`system_prompt_section` stores one ordered collection: `title`, `body`,
`sort_order`, `created_at`, and `updated_at`. Every row is equal. The four
defaults (`Identity`, `Instructions`, `Examples`, `Context protocol`) are
seeded as ordinary rows by migration `e5c1a9d3b7f2` and by
`POST /reset`; they can then be edited, deleted, and reordered like any
owner-authored section. There is no `builtin_key`, no Python-only fallback list,
and no separate built-in endpoint. `GET`, `POST`, `PUT /order`,
`PUT /{section_id}`, `DELETE /{section_id}`, and `POST /reset` under
`/api/v1/agent/settings/system-prompt` manage the whole collection. Title and
body are trimmed and both are required. `sort_order` is used instead of the
SQL-reserved word `order`; reorder rewrites the complete order in one locked
transaction and rejects partial or duplicate id lists. `POST /reset` deletes
every row and inserts the four seed rows with fresh identities.

`create_conversation` reads all non-empty rows in `sort_order, id` order and the
owner's profile once. Every row renders as `system_prompt:<id>`, followed by
`user_profile` when the user set a display name or cards. The combined sections
become one provider system message and are frozen into `pi.system`. Editing,
deleting, or reordering a row affects only new conversations and never rewrites
an existing provider prefix. The list is cached under the `system_prompts` scope
for 30 seconds; writes bump only that scope.

The old singleton `system_prompt` row is migrated into the first section
(`sort_order = 10`) by `c9e1f3a5b7d2`; downgrade copies the first section back
into the singleton table. The old custom/built-in split is removed by
`e5c1a9d3b7f2`: upgrade materializes the effective built-in bodies as rows and
drops `builtin_key`; downgrade restores the column and converts the first row
whose title still matches a canonical default back into an override.

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

### Saved questions

`saved_question` is the owner's Q&A library. It is separate from the immutable
conversation log: a row can be created before an answer exists, and asking it
writes only the latest outcome to that row.

| Column | Type | Notes |
|---|---|---|
| `id` | bigint identity | Primary key |
| `question` | text | Required, trimmed, 1–32,000 characters |
| `answer` | text, nullable | Written only by an ask |
| `citations` | JSONB | Array of citation tokens, default `[]` |
| `conversation_id` | bigint, nullable | FK to `agent_conversation`, `ON DELETE SET NULL` |
| `run_status` | varchar(16), nullable | `running`, `waiting`, `completed`, `failed`, or `cancelled` |
| `error_code` | varchar(64), nullable | Safe error code from the last ask |
| `error_detail` | text, nullable | Safe error detail from the last ask |
| `created_at` | timestamptz | Creation time |
| `updated_at` | timestamptz | Updated by edits and asks |
| `last_asked_at` | timestamptz, nullable | Most recent ask attempt |

CRUD uses the request-scoped transaction and does not resolve the chat
generator, so questions can be captured and edited while AI is not configured.
`GET` returns `{resources, total, limit, offset}`; `limit` is 1–100 (default 50)
and `offset` starts at 0. Rows are ordered by `created_at` descending, then `id`
descending.

`POST` accepts only `question` (`extra=forbid`) and returns `201` with an empty
answer, empty citations, and null run fields. `PATCH` accepts only `question`.
If the normalized text differs from the stored text, the service clears
`answer`, `citations`, `conversation_id`, `run_status`, `error_code`,
`error_detail`, and `last_asked_at`. An unchanged edit only refreshes
`updated_at`. `DELETE` returns `204`; a missing row is
`404 saved_question_not_found` for update, delete, and ask.

`POST /{question_id}/ask` is a regular JSON request, so it may hold the request
session while the turn runs; the agent loop still opens its own short-lived
sessions. The service:

1. Loads the saved question and validates that the chat generator is configured.
2. Creates a new conversation titled from the first 80 characters of the
   question.
3. Appends the saved question as the user entry and calls `collect_turn`.
4. Extracts citation tokens from the final assistant entry and records the
   answer, citations, conversation id, run status, and error fields on the same
   row, updating `last_asked_at`/`updated_at`.

A provider or tool failure is `200` with `run_status="failed"` and its
`error_code`/`error_detail`, so the saved question is retained. A missing AI
configuration is still `503 agent_not_configured`, because the dependency
cannot build the agent service. Asking again creates another conversation and
replaces the stored answer on the same row.

### Tool result preview data

`pi.tool-result.data` is UI-only and is never sent to the provider. It contains
`tool`, `status`, `error_code`, `duration_ms`, validated `arguments`, optional
`resource`, and bounded preview fields. Preview strings are whitespace-normalized
and clipped to 600 characters; lists keep the tool's existing bounds (100 path
entries, 50 timeline events).

| Tool | Preview fields |
|---|---|
| `search_knowledge` | `file_results[].excerpt/viewer_url`, `memory_results[].title/excerpt/viewer_url`, `summary_results[].excerpt` |
| `read_file` | `viewer_url`, `chunks[].excerpt` |
| `read_timeline` | `events[].content`, `events[].summary_id`, nullable `events[].viewer_url` |
| `read_path` | `directories[]`, `files[].viewer_url` |
| `read_memory` | `target` preview, `neighbors[]` previews, plus the id lists |
| `save_memory` | `mode` (`save`/`deprecate`), `memory` preview, `supersedes[]`, or `memory_ids[]` + `deprecated[]` + `reason` for a direct deprecation |
| `present_resource` | `resource` descriptor |
| `web_search` | `results[].title/url/excerpt/score`, `retrieved_at`, `cached`, `truncated` |
| `web_fetch` | `url`, `content_chars`, `retrieved_at`, `cached`, `truncated` |

The live `tool_end` SSE event carries `entry_id`, `tool_call_id`, `name`,
`status`, optional `resource`, the UI-only `data`, `duration_ms`, and
`error_code` fields, plus `parallel`, `batch_size`, and `parallel_index`. The
matching `tool_start` carries the same batch fields. `data` mirrors the persisted
`pi.tool-result` payload, so a live inspector can render the same excerpts,
dimensions, tags, memory previews, and viewer URLs without waiting for a
transcript refetch. Provider-facing tool content remains the separate XML
payload in `model`.

Tool names: `search_knowledge`, `read_file`, `read_timeline`, `read_path`,
`read_memory`, `save_memory`, `present_resource`, `web_search`, `web_fetch`.
The two web tools are read-only. They call the active `web_search` / `web_fetch`
provider, cite the URL and retrieval time, and never send archive-private
content or keys to the provider. `search_knowledge` summary sources and
`read_timeline` summary events carry `view="compressed"`, `memory_count`, and a
`<compressed_view>` child with coverage; the agent must not treat them as the
complete original text.

`save_memory` is a write action and never executes from a model-supplied
confirmation. Its authorization depends on the run's
`save_memory_requires_approval` snapshot:

- **On (default):** valid arguments create a durable `agent_approval` row and
  move the run to `waiting`; the model-supplied `user_confirmed` flag is ignored.
  Only `POST /api/v1/agent/approvals/{id}/approve` executes the write, and it
  passes `approved=True` to the registry. Reject appends a `memory_rejected`
  error result and resumes without writing.
- **Off:** the loop executes the validated call immediately with backend
  authorization (`approved=True`) and the run completes normally. No waiting run
  or approval row is created.

Direct registry calls without that backend flag still return
`memory_confirmation_required`. Disabling the setting does not resolve existing
pending approvals; they remain explicit and their cards keep rendering.

`save_memory` accepts two validated shapes. With `content`, it appends a new
memory (and optionally supersedes old ids). Without `content`, `supersedes` must
be non-empty and the call only deprecates those rows: no replacement is inserted,
`deprecated_at` is stamped, `reason` is stored on each row, the search chunks are
marked non-current, and the approval preview switches to `mode="deprecate"`.
`present_resource` returns `/viewer/file/{id}?chunk={n}` or
`/viewer/memory/{id}` and does not fetch or open the resource.

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
the same folder and `201`. A path occupied by a file returns
`409 tree_path_conflict`. The archive cache version is bumped only when a new
folder is created.

### Move

`move_file` requires a current, non-deleted file id. It normalizes the target,
requires the same extension, and rejects a target occupied by any folder or
current file with `409 tree_path_conflict`. Moving to the current path is an
idempotent `200`.

A move updates `file.raw_file_path` and `file.file_name` in place. The file id,
version, `is_current`, chunks, embeddings, storage key, original bytes, and
history links are unchanged. The folder/file cache version is bumped. Search,
timeline, citations, and viewer links keep working because the id does not
change.

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
| `tree_path_conflict` | 409 | Target is occupied by another folder or current file |
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

The frontend opens files in the File Library preview modal and memories in the
memory reader; legacy `/viewer/file/:fileId` and `/viewer/memory/:memoryId`
links redirect there. PDF, DOCX, image, and text engines are lazy-loaded and
never execute uploaded scripts. Images are served through the normal file
content endpoint.
PDF.js CMaps and standard fonts are copied into `frontend/public/pdfjs` by
`frontend/scripts/copy-pdfjs-assets.mjs`, then emitted into
`frontend/dist/pdfjs` by Vite. The Docker image copies the committed `dist`, so
those generated assets must be committed with the build.

## Account and sessions

The first visit creates the single owner account through
`POST /api/v1/auth/setup`. `GET /api/v1/auth/profile` returns the effective
display name and ordered cards; `PUT /api/v1/auth/profile` replaces the name and
every card atomically. The sign-in username stays immutable. Passwords are
hashed with Argon2; sessions are opaque cookies whose SHA-256 hash is stored in
`user_session`. The cookie is HttpOnly and
SameSite=Lax; set `APSOR_COOKIE_SECURE=true` behind HTTPS. Every knowledge,
settings, and agent endpoint requires the session; `/api/v1/health`,
`/health`, `/api/v1/auth/*`, `/api/docs`, `/api/redoc`, `/openapi.json`, and the SPA
shell are public. There is no password recovery, by design.

## Database

Alembic owns the schema. The initial migration creates `pg_trgm` and six archive
tables: `file`, `folder`, `chunk`, `chunk_ngram`, `memory`, and
`memory_summary` (plus Alembic's own `alembic_version`). Later migrations add
provider settings, the retired standalone media tables, document analysis
fields, account/session auth (`app_user`,
`user_session`), the agent tables (`agent_conversation`,
`agent_entry`, `agent_run`, `agent_approval`) plus the `agent_commit_seq`
sequence, and durable
ingestion (`file_ingest_job`, `ingest_config`). The agent
migration is `a7c41e9d2b60`, after `f3cd26ca9f67`. The page-context migration
`c4f1a9e2b7d3` follows it and updates the entry `kind` and `model` check
constraints to include `pi.page-context`; it does not add a table or column.
The runtime-config migration `e7a1c4b9d2f6` follows `c4f1a9e2b7d3`, creates the
singleton `agent_config` table with all range and cross-field check constraints,
and seeds row `id=1` with the defaults. Later migrations in order:

- `f3c8d5a1b7e2` drops the turn-wide tool-result budget;
- `a6e2f9c4d1b8` raises the per-result tool character cap to 100,000;
- `c9f1a2b3d4e5` raises the default turn budget to 100,000 tokens and the
  compaction threshold to 75,000;
- `b7d2e9c4a1f6` (after `c9f1a2b3d4e5`) creates `saved_question`, including
  its JSONB citation array, check constraints, conversation FK with
  `ON DELETE SET NULL`, and conversation-id index;
- `e2b7c4d9a6f1` (after `b7d2e9c4a1f6`) raises the `max_steps` default from 8
  to 24 and updates an untouched default row;
- `d1e2f3a4b5c6` (after `e2b7c4d9a6f1`) creates the durable `file_ingest_job`
  queue with status/source/range checks, the active-path unique index, and the
  `file` foreign key;
- `d4b8e6f1a2c7` (after `d1e2f3a4b5c6`) creates the singleton
  `ingest_config` table, its range and overlap constraints, and seeds row
  `id=1`;
- `b3e5c7d9f1a2` (after `d4b8e6f1a2c7`) adds `context_window_tokens` with a
  1,000,000 server default and an 8,000–2,000,000 check constraint; existing
  rows receive the default;
- `c8f2a4b6d9e1` (after `b3e5c7d9f1a2`) adds the non-null
  `save_memory_requires_approval` boolean with a `true` server default;
  existing rows receive `true`;
- `f2b3c4d5e6a7` (after `c8f2a4b6d9e1`) creates `agent_approval` with its
  status check, conversation/run/entry foreign keys, status indexes, and the
  partial unique pending `(run_id, tool_call_id)` index;
- `8f4b2c6d9e01` drops the retired `media_ngram` and `media_asset` tables. The
  downgrade recreates their original schema and indexes;
- `c4d8e2f6a1b9` (after `8f4b2c6d9e01`) creates the explicit `folder` table,
  copies current folder rows with their ids, and drops `tree_node`. File leaves
  are derived from `file.raw_file_path`. The downgrade recreates current folders
  and current file leaves;
- `d5e9f3a7b2c1` creates the singleton `system_prompt` table for the
  owner-authored first system section;
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
  `system_prompt_section`, and `app_user.display_name` / `bio`. The old
  successor-only check becomes “successor or direct deprecation timestamp”.
  Downgrade re-adds the old check as `NOT VALID` so direct-deprecated rows are
  preserved;
- `b7e2d4f6a8c1` creates `user_profile_card` with ordered title/content rows,
  migrates `app_user.bio` into an `About` card, and drops the bio column;
- `e5c1a9d3b7f2` (current head) unifies custom sections and built-in overrides
  into one `system_prompt_section` table. The upgrade materializes the effective
  built-in bodies as ordinary rows after the custom rows, deletes the override
  rows, and drops `builtin_key` and its constraints. The downgrade restores the
  column and converts the first row whose title still matches a canonical
  default back into an override; renamed rows stay custom and the old code falls
  back to the Python default for that slot.

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
  worker.py                dedicated durable-ingestion process
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
    domain/                chunking, n-grams, timeline, summary, ingest config
    model/                 SQLAlchemy models (files, chunks, ingest jobs/config)
    repository/            SQL, retrieval, and job-queue queries
    service/               orchestration, indexing, ingest jobs/settings
    router/                HTTP adapters (folders, files, ingest settings)
    schema/                Pydantic request/response contracts
    exception/             stable domain errors
    dependencies.py        composition root
  module/agent/
    domain/                replay builder, compaction, runtime config, envelopes
    model/                 conversation, entry, run, agent_config, saved_question
    protocol/              chat, repository, settings, saved-question protocols
    repository/            transaction, commit sequence, config, saved questions
    service/               agent loop, settings, context, tools, saved questions
    router/                conversation, compact/clear, settings, tools, questions
    schema/                request/response, settings, saved-question contracts
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
PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/apsor-archive-pytest.log
```

The tests use a real PostgreSQL database named `apsor_archive_test` on the same
instance. They run sequentially, reset tables between tests, and treat warnings
as errors. There are exactly ten collected tests:

1. `tests/test_agent.py::test_agent_entry_log_tool_loop_and_cache_usage`
2. `tests/test_errors.py::test_validation_and_error_envelope`
3. `tests/test_file_library.py::test_file_ingest_path_read_and_soft_delete`
4. `tests/test_memories.py::test_save_memory_supersede_and_trace`
5. `tests/test_search.py::test_hybrid_search_and_union_query`
6. `tests/test_summaries.py::test_summary_fallback_and_search`
7. `tests/test_system.py::test_health_gzip_and_cache_invalidation`
8. `tests/test_system_prompt.py::test_system_prompt_module_and_section_order`
9. `tests/test_timeline.py::test_timeline_sparse_sampling`
10. `tests/test_versions.py::test_file_history_and_versioning`

The agent test injects a deterministic `FakeChatGenerator` by assigning
`client.app.state.agent_chat_generator`; no DeepSeek or OpenAI request is made.
It also covers runtime settings defaults, full PUT and reset, validation
failures (`400 invalid_request`), runtime snapshot handling for later runs, auto
and manual compaction, clear, the page-context boundary and same-page
reattachment, retry, forking at the latest and at a specific entry (parent
fields, new provider session id, entry isolation, head/edit remapping, source
immutability, archived/busy/cutoff validation), parallel versus sequential tool
execution, human save-memory approval, the approval toggle, and the
saved-question library. Approval coverage asserts that the default `true` path
creates a waiting run and pending row with no memory write before approval,
model `user_confirmed=true` does not bypass it, a valid waiting run survives a
fresh app lifespan, approve writes exactly once and appends the result,
duplicate approve/reject returns `409`, reject writes nothing, an orphaned
waiting run fails closed on restart, and an archived conversation fails closed.
Toggle coverage asserts that `false` skips the waiting run and approval row,
saves memory directly with backend authorization even when the model sends
`user_confirmed=false`, completes the run, and that changing the setting never
resolves an existing pending row. Saved-question coverage includes
create/list/pagination, ask success, a failed ask that keeps the row with
`run_status="failed"` and error detail, edit resetting the answer and
conversation link, delete, not-found errors, and the `conversation_id`
`ON DELETE SET NULL` result. The
file library test covers idempotent folder creation, in-place moves, independent
copies, extension checks, and path conflicts. It also exercises the durable
queue: async enqueue for text and upload, worker claim and processing, progress
fields through `ready`/`failed`, the rule that a failed job publishes no
current file or chunks, the synchronous fallback, and the ingestion settings
read/PUT/reset contract. The retry endpoint was also exercised manually against
a failed job. The file-library test also uploads an image without a vision
provider and checks the filename caption, stored original, path listing, and
search result. The provider test creates multiple saved rows per capability,
proves the partial unique active index, clears a key without ever returning
plaintext, exercises the injected `app.state.provider_tester`, and verifies an
identity id is not reused after delete. The agent test injects a deterministic
`app.state.web_research_service` and asserts the `web_search` / `web_fetch` XML,
plus the compressed-summary markers. The system-prompt test covers the four
seeded defaults as ordinary rows, create/list/reorder/update/delete/reset,
`system_prompt:<id>` composition order, frozen old conversations, editing and
deleting defaults, reset restoring fresh default identities, whitespace and
partial-reorder validation, identity non-reuse, and scoped cache invalidation;
it also covers the frequently used prompt CRUD, whitespace validation, the
20-row cap, ordering, and scoped cache invalidation.

A separate manual validation used the public-domain 《紅樓夢》 from Project
Gutenberg (about 2.66 MB, 268 chunks at 4,000 characters / 500 overlap) against
the real DeepSeek API. Turns answered questions about Baoyu and Daiyu's
past-life debt and 還淚, the stone's descent and 通靈寶玉, and the ending where
寶玉 leaves with the monk and the Taoist, with citations such as
`[file:27#...]`. That run is evidence, not a committed test fixture.

The suite does not execute migrations; upgrade and downgrade are separate
checks against the development database. Runtime settings and compaction are
validated by Pydantic, the frozen `AgentRuntimeConfig`, and PostgreSQL check
constraints.
