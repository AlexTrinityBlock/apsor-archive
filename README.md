<div align="center">
  <img src="frontend/public/favicon.svg" alt="DendroMatrix" width="112" height="112">
</div>

<h1 align="center">DendroMatrix</h1>

<p align="center">
  A local-first knowledge and memory archive for files, memories, and the media between them.
</p>

<p align="center">
  <a href="https://github.com/AlexTrinityBlock/dendromatrix"><img src="https://img.shields.io/badge/version-0.1.0-171717" alt="Version 0.1.0"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/AlexTrinityBlock/dendromatrix?label=license&amp;color=171717" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/self--hosted-yes-171717" alt="Self-hosted">
  <a href="https://github.com/AlexTrinityBlock/dendromatrix/pulls"><img src="https://img.shields.io/badge/PRs-welcome-171717" alt="Pull requests welcome"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&amp;logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/react-19-61DAFB?logo=react&amp;logoColor=black" alt="React 19">
  <img src="https://img.shields.io/badge/vite-8-646CFF?logo=vite&amp;logoColor=white" alt="Vite 8">
  <img src="https://img.shields.io/badge/bun-1.3.6-fbf0df?logo=bun&amp;logoColor=black" alt="Bun 1.3.6">
  <img src="https://img.shields.io/badge/postgresql-17-4169E1?logo=postgresql&amp;logoColor=white" alt="PostgreSQL 17">
  <img src="https://img.shields.io/badge/docker%20compose-2496ED?logo=docker&amp;logoColor=white" alt="Docker Compose">
</p>

A local-first knowledge and memory archive with a branching file library, a
linear memory timeline, hybrid retrieval, and grounded AI answers.

DendroMatrix is not a note list. It is a retrieval surface designed for a small
number of deliberate tool calls: search a passage, read its neighbours, walk the
path, sample a season, press a new memory, or trace a superseded one. Every
result carries its source, chunk number, and time.

> Status: v0.1.0 — file/memory/media archive, owner login, persistent
> Pi-shaped agent with database-backed runtime limits, compaction, parallel
> tools, SSE chat, a saved-question Q&A library, durable async ingestion,
> dedicated PDF/DOCX/image/text viewers, a folder workspace, and a three-state
> agent dock.

## Highlights

- **Files have lineage.** A path is a branch, not an overwrite. Re-uploading a
  file grows a new leaf; the previous edition remains addressable as history.
- **Ingestion is durable.** An upload or direct text can return a
  `file_ingest_job` immediately while a bounded worker parses, chunks, embeds,
  and publishes it. The queue survives restarts, reports progress, and never
  exposes a half-indexed file.
- **The library is a folder workspace.** Folders are first-class: create them in
  place, drop files onto a folder card to upload, drag a file card onto another
  folder to move it, and use an explicit Copy action when you want an
  independent second record.
- **The agent stays within reach.** A global dock collapses to a seal, opens as
  a compact chat panel, or expands into a split desk where the current tool call
  is inspected beside the conversation.
- **Page context respects the cache.** A plain-text snapshot of the current page
  is appended only when the page key changes, in the same commit as the user
  message, so earlier entries and the KV-cache prefix stay untouched.
- **Agent limits are database-backed.** The turn budget, compaction threshold,
  step and tool caps, parallel width, and result budgets live in one validated
  `agent_config` row and apply to new runs without a restart.
- **Long threads can be folded or cleared.** Compaction writes a summary
  boundary; clear starts an empty active context. The full transcript remains
  readable in both cases.
- **Memories are linear and traceable.** A new belief can supersede an old one.
  The old memory leaves the search surface but stays readable through its chain.
- **Search is hybrid.** BM25 over CJK bigrams and Latin tokens runs beside vector
  recall. Results are de-duplicated and fused, with the reason recorded.
- **Time is sampled honestly.** A timeline returns up to five anchors per event
  kind and reports exactly how many events were skipped.
- **AI answers are grounded.** DeepSeek receives retrieved passages, not the
  whole library, and every claim must carry a citation. Without a key, the
  answer endpoint fails closed.
- **Questions outlive the conversation.** Save a question before you have an
  answer, ask it later, and keep the answer, its citations, the run status, and
  a link to the conversation on the same row. Editing the question clears the
  stale answer instead of leaving a mismatched pair on screen.
- **Images have their own archive.** A standalone media index turns images into
  captions, OCR text, and visual fingerprints. Text search reaches the captions;
  image search compares visual descriptors. It never mixes with the text chunk
  tree.
- **Documents choose their extractor.** PDFs try text first and fall back to
  vision for scanned pages. DOCX, TXT, JSON, CSV, and logs use text, with AI
  structured metadata; images use vision.
- **The archive is local and single-owner.** It binds to `127.0.0.1` by default
  and is protected by one owner account with an Argon2 password hash and an
  HttpOnly session cookie. Run it on your own machine; put it behind Cloudflare
  Tunnel only with your own access controls.

## Stack

| Layer | Choice |
|---|---|
| API | Python 3.13, FastAPI, SQLAlchemy 2 async, Alembic, psycopg 3 |
| Storage | PostgreSQL 17 (`pg_trgm` for path fuzzy search) |
| Cache | Valkey / Redis-compatible, with a memory fallback |
| Retrieval | CJK bigram + Latin token n-grams, BM25, signed hashing vectors, RRF |
| AI | DeepSeek `deepseek-flash` (OpenAI-compatible chat completions) |
| Frontend | React 19, TypeScript, Vite, React Router, React Query, Orval |
| Deploy | Docker Compose, optional Cloudflare Tunnel, or bare metal with `uv` |

## Quick start

### Docker Compose (normal)

```bash
docker compose up --build
```

Open <http://127.0.0.1:8000>. The first visit asks you to create the single
owner account. Once signed in, an empty archive offers a demo seed. The database
and file data live on named volumes.

The API image copies the committed `frontend/dist`; it does not run a frontend
build. After changing frontend code, run `cd frontend && bun run build` before
`docker compose up --build`.

To enable AI answers and AI summaries:

```bash
mkdir -p .secrets
printf 'DENDRO_DEEPSEEK_API_KEY=sk-your-key\n' > .secrets/deepseek.env
chmod 755 .secrets
chmod 644 .secrets/deepseek.env
docker compose up -d --build
```

The Compose file mounts `.secrets/` read-only. The app reads the env file itself,
so the key never becomes a container environment variable and never appears in
`docker compose config`. The `644` mode is required because the API container
runs as a non-root user. The key is gitignored and is never returned by the API.
Without it, summaries fall back to a deterministic extractive form,
`POST /api/v1/ask` returns `503 ai_not_configured`, and agent messages return
`503 agent_not_configured`.

### Configure AI in the app

The Settings page is the normal way to configure providers. It writes to the
`ai_provider_config` table:

- **Chat** — DeepSeek or any OpenAI-compatible chat endpoint.
- **Embedding** — offline `hashing`, or `openai` / `openai-compatible`.

The API key is encrypted with Fernet before it is stored. The browser only ever
receives a hint such as `...14f8`; the plaintext key is never returned, logged,
or written to Compose output. `DENDRO_SECRET_KEY` supplies the encryption master
key. If it is unset, a `0600` key file is created at `data/.secret_key` (or
`/data/.secret_key` in Docker), so the encrypted values survive restarts.

Precedence is: **database row → environment → built-in default**. The Settings
page labels each provider with its source. Changing the embedding model does not
rewrite existing vectors; `reindex_required` warns you. Run **Re-embed library**
(or `POST /api/v1/settings/ai/embedding/reindex`) to refresh current chunks.
Vector search skips chunks whose dimension does not match the current embedder.

AI settings API:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/settings/ai` | Both provider slots, masked hints, source, reindex advice |
| `PUT` | `/api/v1/settings/ai/{purpose}` | Create/update `chat` or `embedding` |
| `POST` | `/api/v1/settings/ai/{purpose}/test` | One small provider request + latency |
| `DELETE` | `/api/v1/settings/ai/{purpose}/key` | Remove the stored key |
| `POST` | `/api/v1/settings/ai/embedding/reindex` | Re-embed every current chunk with the active provider |

### Agent runtime settings

The **Agent runtime** panel on `/settings` edits the singleton `agent_config`
row (`id=1`). Provider and model selection stay in the AI settings above, so
there is still one source of truth for which model answers. All eleven runtime
values are stored in PostgreSQL and apply to new runs without a restart.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/agent/settings` | Effective config, defaults, source, `updated_at` |
| `PUT` | `/api/v1/agent/settings` | Full replacement; all eleven fields are required |
| `POST` | `/api/v1/agent/settings/reset` | Persist and return the built-in defaults |

The generated operations are `getAgentSettings`, `updateAgentSettings`, and
`resetAgentSettings`.

The read shape is `{config, defaults, source, updated_at}`, where `source` is
`database` for a stored row or `default` when the API had to create or repair the
row from defaults. `PUT` requires a complete snapshot: omitted fields and extra
fields are rejected.

| Field | Default | Range |
|---|---|---|
| `max_total_tokens` | 100,000 | 8,000–200,000 |
| `compaction_threshold_tokens` | 75,000 (~75%) | 1,000–200,000 |
| `max_steps` | 24 | 1–32 |
| `max_tool_calls_per_turn` | 6 | 1–24 |
| `max_parallel_tools` | 6 | 1–24 |
| `max_tool_result_chars` | 100,000 | 1,000–200,000 |
| `max_page_context_chars` | 6,000 | 500–50,000 |
| `max_compaction_summary_chars` | 6,000 | 1,000–20,000 |
| `max_compaction_last_user_chars` | 4,000 | 500–10,000 |
| `auto_compaction_enabled` | `true` | boolean |
| `parallel_tools_enabled` | `true` | boolean |

Pydantic and matching PostgreSQL check constraints enforce the ranges and two
cross-field rules: the compaction threshold must be lower than the total token
budget, and the parallel width must not exceed tool calls per turn. The app's
global validation envelope maps request validation failures to `400
invalid_request` rather than 422.

A request loads one immutable runtime snapshot in a short-lived database session.
An active SSE run keeps the snapshot it started with; later runs use changed
settings. The backend contract is described in `backend/README.md`.

### Ingestion runtime

The synchronous `POST /api/v1/files` and `POST /api/v1/files/text` endpoints
remain, but the UI can enqueue work instead. The async routes store the payload
and return `202` with an `IngestJobSchema`:

| Method | Path | Operation |
|---|---|---|
| `POST` | `/api/v1/files/async` | `uploadFileAsync` |
| `POST` | `/api/v1/files/text/async` | `createTextFileAsync` |
| `GET` | `/api/v1/files/ingest-jobs?limit=&offset=` | `listIngestJobs` |
| `GET` | `/api/v1/files/ingest-jobs/{id}` | `getIngestJob` |
| `POST` | `/api/v1/files/ingest-jobs/{id}/retry` | `retryIngestJob` |

A job moves through `queued(0)`, `parsing(5)`, `chunking(15–20)`,
`embedding(25–90)`, `summarizing(95)`, and `ready(100)`, or ends as `failed`.
`progress_pct`, `chunks_total`, and `chunks_embedded` are durable, so a reloaded
page can resume the same display. Staged file and chunk rows are published only
when the job is ready; a failed job keeps its error but exposes no partial
current file.

One worker process polls the database every second while idle and claims queued
rows with `SELECT ... FOR UPDATE SKIP LOCKED`. It runs two extraction threads
and at most two in-flight jobs, with global async embedding concurrency of six
and batched progress updates. Stale jobs are requeued after a crash, and
embedding retries are bounded. The API lifespan starts one worker for local use;
run a dedicated process in production:

```bash
cd backend
uv run dendromatrix worker
# or
uv run python -m app.worker
# process at most one job, then exit
uv run python -m app.worker --once
```

The standard and Cloudflare Compose stacks run this as a dedicated `worker`
service and set `DENDRO_INGEST_WORKER_ENABLED=false` on the API, so exactly one
process owns the queue.

The **Ingestion runtime** panel on `/settings` edits the singleton
`ingest_config` row. It is a full replacement, not a patch, and the read body
carries `{config, defaults, source, updated_at}` with a Database/Defaults badge.

| Method | Path | Operation |
|---|---|---|
| `GET` | `/api/v1/settings/ingest` | `getIngestSettings` |
| `PUT` | `/api/v1/settings/ingest` | `updateIngestSettings` |
| `POST` | `/api/v1/settings/ingest/reset` | `resetIngestSettings` |

| Field | Default | Range |
|---|---|---|
| `poll_seconds` | 1.0 | 0.25–30 |
| `extract_workers` | 2 | 1–8 |
| `max_inflight_jobs` | 2 | 1–4 |
| `embedding_concurrency` | 6 | 1–32 |
| `chunk_target_chars` | 4,000 | 1,000–20,000 |
| `chunk_overlap_chars` | 500 | 0–5,000; below target |

The worker reads a fresh database snapshot each loop and job, so saved worker
changes apply without a restart; a job already running keeps its snapshot.
Environment values seed a fresh install and remain the fallback. Changing chunk
sizes affects only future ingests. The backend contract is described in
`backend/README.md`.

### Local development

```bash
# 1. PostgreSQL + Valkey
docker compose -f docker-compose.dev.yml up -d --wait

# 2. API
cd backend
uv sync
uv run alembic upgrade head
uv run dendromatrix --reload

# 3. Frontend (second terminal)
cd frontend
bun install
bun run dev
```

Vite runs on <http://127.0.0.1:5173> and proxies `/api` to the API. To build the
client that the container serves:

```bash
cd frontend && bun run build
```

`./start.sh` is the shortest bare-metal path: it starts the dev database/cache
if Docker is available, sources `.secrets/deepseek.env`, syncs the backend, and
serves the API and committed client at <http://127.0.0.1:8000>.

### Cloudflare Tunnel

This is the **Tunnel** deployment variant. A future pure Cloudflare Serverless
deployment should use its own compose file; the tunnel stack stays in
`docker-compose.cloudflare-tunnel.yml`. It publishes no host port. `cloudflared`
connects to a non-root Caddy reverse proxy, which forwards to the API.

```bash
mkdir -p secrets
# Write the tunnel token; no trailing newline.
printf '%s' 'your-tunnel-token' > secrets/cf_token.txt
chmod 644 secrets/cf_token.txt
export DENDRO_PUBLIC_HOST=archive.example.com
docker compose -f docker-compose.cloudflare-tunnel.yml up -d --build
```

Point the tunnel ingress for `archive.example.com` at `http://caddy:80`. The
token file is gitignored. See `secrets/README.md` for permissions and
[`docs/cloudflare-tunnel.md`](docs/cloudflare-tunnel.md) for the complete
English deployment, backup, security, and troubleshooting guide.

## Tool surface

The archive exposes six small HTTP tools. Each JSON endpoint mirrors a retrieval
or memory operation the agent can call; each payload is deliberately small enough
for an LLM to use in sequence.

| Tool | Endpoint | What it returns |
|---|---|---|
| `search_knowledge` | `GET /api/v1/search?query=&result_number=2` | Top results per source kind from BM25 + vector, fused with RRF and deduplicated |
| `read_file` | `GET /api/v1/files/{file_id}/chunks/{chunk}?chunk_range=1` | A 1-based chunk window |
| `read_timeline` | `GET /api/v1/timeline?year=&month=&day=&day_range=1` | Up to five sampled events per kind, density, and skip counts |
| `read_path` | `GET /api/v1/paths?path=/history&path_depth=1&fuzzy_search=` | Directories and files, or fuzzy path matches |
| `save_memory` | `POST /api/v1/memories` | A new memory, the deprecated memories it replaced, and any new summary |
| `read_memory` | `GET /api/v1/memories/{memory_id}?memory_range=1&trace_history=true` | Target, neighbours, supersedes, successor, and chain |

The persistent archive agent exposes nine model tools: the six above plus
`search_media`, `get_media`, and `present_resource`. The HTTP examples use
explicit parameters; the HTTP server defaults are `result_number=2`,
`chunk_range=1`, `day_range=1`, `path_depth=1`, and `memory_range=0`. Text is chunked at about 4,000 characters with a 500-character overlap; existing files keep their original chunk boundaries until re-ingested. The agent's
tool schemas choose their own defaults, such as `result_number=8` and
`day_range=7`. For external LLM callers, the separate `/api/v1/tools/*` facade
renders the same services as compact XML; the persistent agent calls the
services directly through its own registry.

`present_resource` returns a viewer URL such as `/viewer/file/{id}?chunk={n}`,
`/viewer/media/{id}`, or `/viewer/memory/{id}` and never fetches the resource.

Persisted `pi.tool-result` entries also carry UI-only `data`: bounded excerpts,
dimensions, tags, and viewer URLs for the expanded inspector. This payload never
enters the provider message; the model still sees only the XML tool result.

`save_memory` is a write action. The tool requires `user_confirmed=true` and the
system prompt instructs the model to save only after an explicit user request
and confirmed wording. The model supplies that flag; there is no separate
approval dialog in the chat UI yet, so this is prompt-enforced rather than a
human-in-the-loop gate. The expanded inspector shows the resulting receipt; it
does not approve the write.

Additional surfaces: `POST /api/v1/files` (multimodal intake), `POST
/api/v1/files/text`, `DELETE /api/v1/files/{file_id}`, `GET /api/v1/paths`,
`GET /api/v1/tree`, `GET /api/v1/memories`, `POST /api/v1/memories`,
`POST /api/v1/summaries`, `GET /api/v1/stats`, `POST /api/v1/demo/seed`,
`GET /api/v1/health`, `GET /api/v1/ai/status`, and `POST /api/v1/ask`.

### Folder workspace

`/library` is a folder-first workspace. A breadcrumb and folder rail describe
where you are; the main area shows folder cards and file cards for the current
path. The previous table remains available as a compact list view for dense
browsing, and it is the fallback layout on narrow screens.

- **New folder** creates the requested folder and any missing ancestors. The
  operation is idempotent: repeating it returns the same folder with `201`.
- **Drag upload** accepts files dropped from the desktop onto a folder card or
  the current folder surface. The upload uses the same intake path, extension
  allowlist, and server limits as the upload dialog: 10 MB per uploaded file
  and `.md`, `.markdown`, `.txt`, `.csv`, `.json`, `.log`, `.pdf`, `.docx`,
  `.jpg`, `.jpeg`, `.png`, or `.webp`. The dialog also supports a 2 MB
  plain-text creation. Dropped files are never opened or executed.
- **Move versus copy** is explicit. A normal drag onto a folder moves the file;
  holding Alt/Option while dropping copies it. Touch and keyboard users get
  separate **Move** and **Copy** actions instead of drag.
- A **move** keeps the same file id, version, chunks, embeddings, and original
  bytes. Only `raw_file_path`, the file name, and the tree node location change,
  so existing search, timeline, citation, and viewer links remain valid.
- A **copy** creates a new current file id at version 1, clones the stored
  original when one exists, rebuilds chunks and embeddings, and copies the AI
  summary, tags, document type, and extraction method. Both files remain
  current and searchable.
- Moves and copies must keep the original extension. A target occupied by
  another current node returns `409 tree_path_conflict`; an invalid path or a
  changed extension returns `422 invalid_path`.

| Method | Path | Body | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/folders` | `{path}` | Create a folder and missing ancestors; idempotent `201` |
| `POST` | `/api/v1/files/{file_id}/move` | `{path}` | Move one current file in place; `200` |
| `POST` | `/api/v1/files/{file_id}/copy` | `{path}` | Copy one current file to a new record; `201` |

All three endpoints require the owner session and bump the archive cache version
when they change the tree or file index.

### Agent conversations

`/api/v1/agent` is a persistent, Pi-shaped multi-turn archive agent. It stores an
immutable entry log instead of mutating a chat array:

- `agent_conversation` — transcript scope, provider/model identity, and metadata.
- `agent_entry` — immutable `pi.user`, `pi.assistant`, `pi.tool-result`,
  `pi.page-context`, `pi.system`, `pi.reset`, `pi.compaction`, and `ui.notice`
  entries. `model` is exactly the provider payload; `data` is UI/diagnostics
  only.
- `agent_run` — durable state for one submission (`request_id`, status, abort,
  last entry, safe error). `agent_commit_seq` groups entries written in one
  transaction.
- `agent_config` — the singleton runtime configuration (`id=1`) holding the
  validated token, step, tool, page-context, and compaction limits.

The first entry is a frozen `pi.system` prompt and tool snapshot. The context
builder replays entries deterministically: it honors `head_entry_id` and `edits`,
keeps system entries, moves tool results directly after their assistant call,
synthesizes missing results, drops orphan results, and excludes failed assistant
attempts. Tool calls are validated and returned as structured results; a tool
failure never becomes an HTTP 500.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/agent/conversations` | Create a conversation and its system entry |
| `GET` | `/api/v1/agent/conversations` | List active/archived conversations, newest activity first |
| `GET` | `/api/v1/agent/conversations/{conversation_id}` | Metadata plus the first entry page |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/entries?after_id=&limit=` | Ascending entry page |
| `PATCH` | `/api/v1/agent/conversations/{conversation_id}` | Rename, archive, or restore |
| `DELETE` | `/api/v1/agent/conversations/{conversation_id}` | Soft delete; entries stay for audit |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/compact` | Append a manual compaction boundary |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/clear` | Append a reset boundary; transcript is preserved |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/messages` | Append a user entry and run the loop |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/retry` | Retry the latest failed/cancelled run |
| `GET` | `/api/v1/agent/tools` | Current tool catalog plus prompt/tools versions |

`POST /api/v1/agent/conversations/{conversation_id}/messages` accepts
`{content, request_id?, page_context?}` and `.../retry` accepts
`{request_id?}`. Both stream `text/event-stream` by default. The event names are
`run_start`, `message_start`, `message_delta`, `message_end`, `tool_start`,
`tool_end`, `run_end`, and `error`. `run_start` reports
`page_context_entry_id` (or `null`) and `page_context_attached` so the client can
mark whether a new snapshot was written. `tool_start` and `tool_end` also carry
`parallel`, `batch_size`, and `parallel_index` for the assistant call batch.
`tool_end` carries the persisted tool-result `data` payload plus `duration_ms`
and `error_code`, so the inspector can render previews before the transcript
refetch settles. `message_start` has `entry_id=null` because the assistant entry
is persisted only at `message_end`; deltas are transport-only. Send
`Accept: application/json` for the completed turn instead. SSE responses set
`Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`, and
Starlette's GZip middleware excludes `text/event-stream`.

Each conversation allows one active run at a time. The defaults allow 24 model
steps, 6 tool calls per user turn, 6 parallel tools, 100,000 total tokens per turn
(cumulative across model steps), and 100,000 result characters per tool. Each
result is clipped independently at that per-result cap with a visible
`[truncated]` marker; there is no turn-wide result budget or second summarization
call. A 100,000-character cap spans roughly twenty-five 4,000-character chunks.
These are runtime settings, not code constants; see **Agent runtime settings**
above. Eligible tool calls start together and execute through `asyncio.gather`
when parallel tools are enabled. Result persistence and `tool_end` order follow
assistant call order, not completion order. When parallel tools are disabled,
execution is sequential and the events report `parallel=false`.

A failed or cancelled run can be retried without duplicating the user entry. The
chat desk and the docked agent expose a Retry action when the latest entry is a
failed/cancelled assistant answer, a trailing hard-limit tool result
(`step_limit`, `token_limit`, `tool_call_limit`, or
`tool_result_budget_exhausted`), or the last stream failed before an assistant
entry was recorded. Retry starts a new run for the same user entry; the UI does
not append a second message and disables the action while a stream is active. A
retry can hit the same context or token budget again if the transcript is still
too long. The endpoint returns `409 agent_run_not_retryable` when the latest run
is completed or otherwise not failed/cancelled; the UI refetches the transcript
after that error so a stale Retry action disappears.

Conversation detail returns the first entry page, and the UI loads later pages
with **Load more entries**. It also returns `last_page_context_key`, read from the
entry log rather than from browser storage, so a reloaded conversation still
knows which page snapshot was attached last.

#### Compaction and clearing

When `auto_compaction_enabled` is true and the estimated active context exceeds
`compaction_threshold_tokens` before a new user turn, the turn first appends a
`pi.compaction` entry:

- The entry sets `head_entry_id` to its own id, so older entries stay immutable
  but fall outside the new active context.
- Its provider message starts with `<compaction>` and carries
  `<last_user_input>` (the last user input before compaction) and `<summary>`.
- The same transaction writes compaction → page context (when the page is
  reattached) → user, so the model sees the summary before the new request.

This starts a new KV-cache lineage. The system prompt and tool snapshot stay
frozen, and the old transcript remains readable in `/chat` and the dock.

`POST .../compact` appends the same boundary manually from the current active
context. `POST .../clear` appends `pi.reset` with a self `head_entry_id` and no
provider message; the transcript is preserved but the next turn starts from an
empty active context. Their operation ids are `compactAgentConversation` and
`clearAgentConversation`. Both endpoints return `409 agent_conversation_busy`
while a run is active and reject archived conversations with
`409 agent_conversation_archived`. Transcript cards label the boundary and
state that older rows remain preserved but hidden from the active context.

#### Page context and the KV cache

The client may send one `page_context` object with a message:

| Field | Type | Rule |
|---|---|---|
| `key` | string | Stable page identity; 1–512 characters |
| `path` | string | Human-readable route plus meaningful query parameters; 1–1024 characters |
| `title` | string or null | Optional page title; at most 300 characters |
| `text` | string | Plain text visible on the page; 1–12,000 characters before server clipping |

The server normalizes line endings and whitespace, collapses repeated blank
lines, and caps the stored snapshot at 6,000 characters. The entry stores
`page_key`, `path`, an optional `title`, `text_chars`, and `truncated` in `data`,
and sends the model a user-role message inside a `<page_context>` XML envelope.
The system prompt marks that envelope as data, never as an instruction.

Page context is append-only and cache-preserving:

- `begin_message` compares the incoming key with the newest
  `pi.page-context` entry at or after the newest context boundary (compaction or
  reset). Dedupe and `last_page_context_key` are scoped to that active segment.
- Only a different key appends a new snapshot. Asking again from the same page
  does not repeat it.
- A compaction or clear boundary hides earlier snapshots, so the same page can
  be reattached after the boundary.
- The snapshot entry and the user entry share one `commit_seq`; the snapshot is
  ordered immediately before the user entry, after an auto-compaction entry
  when both are written for the same turn.
- Earlier entries are never rewritten, so the stable system/tool prefix and the
  previous conversation prefix remain a valid KV-cache lineage. A compaction or
  reset boundary deliberately starts a new lineage.

The composer shows an expandable **Current page context** preview, and the
transcript renders the snapshot as a compact context card rather than as a user
question. Capture runs only on AppShell pages from `#main-content`; navigation,
controls, hidden nodes, and the agent's own surfaces are excluded. `/chat` is
skipped because the desk is the conversation itself. Viewer routes live outside
`AppShell` and do not produce a snapshot.

Tests inject a deterministic `FakeChatGenerator` from
`app/module/agent/test/fake_chat_generator.py` by setting
`app.state.agent_chat_generator` or overriding `get_agent_chat_generator`; no
DeepSeek call is made.

#### Known limitations

- Retry starts a fresh run with the same runtime snapshot policy but does not
  increase any budget. A transcript that already exhausted the token or tool
  result budget can reach the same limit again.
- `save_memory` is still prompt-enforced. The `user_confirmed=true` flag is
  supplied by the model; there is no separate human approval dialog.
- `agent_run.waiting` remains reserved for a future resume/approval flow; the
  current loop emits only running, completed, failed, and cancelled.

### Saved questions

`/api/v1/agent/questions` is a small Q&A library beside the conversation agent.
A saved question can exist before any answer exists. Asking it creates a new
conversation, runs one JSON agent turn, and writes the result back to the same
row, so the question keeps a stable id and its latest answer.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/agent/questions?limit=&offset=` | List saved questions newest first; `limit` is 1–100 (default 50) |
| `POST` | `/api/v1/agent/questions` | Save a question; `201`; accepts `question` only |
| `PATCH` | `/api/v1/agent/questions/{question_id}` | Edit the question text |
| `DELETE` | `/api/v1/agent/questions/{question_id}` | Delete the question and its stored answer; `204` |
| `POST` | `/api/v1/agent/questions/{question_id}/ask` | Run one turn and persist its outcome |

The list body is `{resources, total, limit, offset}`. All five operations require
the owner session. Create and update reject unknown fields, so a client cannot
supply an answer. `question` is trimmed and limited to 32,000 characters.

The table (`saved_question`) stores:

- `id`, `question`, nullable `answer`, and `citations` as a JSONB array;
- nullable `conversation_id` with `ON DELETE SET NULL`, so deleting the
  conversation keeps the saved answer;
- `run_status`, `error_code`, and `error_detail` for the latest ask;
- `created_at`, `updated_at`, and `last_asked_at`.

`PATCH` compares the normalized text with the stored text. A changed question
clears `answer`, `citations`, `conversation_id`, all run metadata, and
`last_asked_at`; an unchanged edit only refreshes `updated_at`. This prevents an
old answer from being shown against new wording.

`POST .../ask` creates a new conversation titled from the question (up to 80
characters), appends the user entry, runs exactly one agent turn with the
existing runtime snapshot policy, and records the final answer, citation
tokens, conversation id, and `run_status`. A provider or tool failure is still
`200` with `run_status="failed"` and its `error_code`/`error_detail`, so the
question survives. A missing AI configuration keeps the existing
`503 agent_not_configured` response. Asking the same question again creates
another conversation and replaces the answer on the same saved row.

The `/questions` page under **Studio** uses the generated hooks and provides
create, list, pagination, edit, delete, and ask actions. Each card shows its
status, answer, citation chips, run error, last-asked time, and an **Open
conversation** link when a conversation exists. Ask is a synchronous JSON
request, so the card shows a pending state for the seconds the turn takes.

### Chat reading room

`/chat` and `/chat/:conversationId` are the persistent reading room for the
agent. The thread rail lists active and archived conversations and supports
rename, archive/restore, delete, and a new thread; the sheet renders immutable
entries as keeper marginalia, archive sheets, field-note tool results, and
structured resource cards. The composer streams over SSE, supports
Cmd/Ctrl+Enter and a stop action, and refreshes the thread list plus the active
transcript when the run settles (other conversations are not refetched).

The thread card shows **Retry** for the latest failed/cancelled assistant, a
trailing hard-limit tool result (`step_limit`, `token_limit`,
`tool_call_limit`, or `tool_result_budget_exhausted`), or a stream failure
before an assistant entry. Retry calls the existing retry endpoint, reuses the
same user entry, does not append a duplicate message, and is disabled while a
stream is active. A `409 agent_run_not_retryable` response triggers a transcript
refetch so the stale action disappears; a retry may hit the same budget again.

The same desk exposes **Compact** and **Clear** for the active context. Compact
is immediate; Clear asks for one inline confirmation. Both are disabled while a
stream runs and on archived threads. A `409 agent_conversation_busy` response
shows the stable error message and refetches the thread. The following
compaction/reset boundary renders as a context card instead of a user message,
and the card states that older transcript rows are preserved but hidden from the
model's active context.

The UI uses the generated Orval hooks for conversation metadata and lifecycle,
and a small `agent-stream.ts` client for `text/event-stream` because generated
hooks resolve normal JSON responses. Markdown is rendered with `skipHtml`;
citations link only to known viewer paths. `/ask` remains available as Quick ask.

Chat appears in the **Studio** navigation and the command palette. On mobile the
bottom tabs remain Overview, Search, Timeline, Library, and More; Chat and the
thread rail are reached from the navigation drawer.

### Agent dock

The global agent dock lives inside `AppShell` but outside `<main>`, so it is
available on every archive page except `/chat` without becoming part of the
captured page text. `/chat` keeps the full-page desk as the single composer for
that route. The dock has three states:

- **Collapsed** — a floating seal in the lower-right corner.
- **Panel** — a compact chat panel with recent conversations, the live stream,
  and the composer.
- **Expanded** — a full-screen split desk. The left column holds the
  conversation, status bubbles, and composer; the right column is an inspector
  that follows the current tool call.

The selected state is stored locally and survives a reload. **Expand** from the
panel opens the same conversation in the split desk instead of starting a new
thread; `/chat` remains the full-page reading room. On mobile the collapsed
state opens a full-height sheet, and the layout must not introduce horizontal
overflow.

The dock uses the same retry decision and `RetryBar` as `/chat`, so a failed or
hard-limited latest turn can be retried from either surface without appending a
second user entry. Compact and clear controls live on the full `/chat` desk.

Status bubbles describe observable work, not hidden chain-of-thought:
orienting, searching, reading, comparing, composing, saving, sealed, and error.
Each row can show the step, tool name, elapsed time, status, and a short result
summary.

The expanded inspector keeps the resource the user is reading on screen. It
follows the newest tool call until the user pins a panel, offers **Follow
current** to resume following, and retains the last valid resource when a later
tool has no resource. Inspector panels reuse the same safe renderers and viewer
queries as the standalone `/viewer/...` routes rather than adding a second
rendering path.

| Tool | Inspector idea |
|---|---|
| `search_knowledge` | Result constellation across files, memories, and summaries; excerpts open in place |
| `read_file` | Manuscript chunk window with file id, chunk number, and citation |
| `read_timeline` | Time band with density, sampled events, and skip counts |
| `read_path` | Folder branch map that opens a folder or file directly |
| `read_memory` | Pressed-leaf memory chain with supersession neighbours |
| `save_memory` | Wax-seal receipt with status, memory id, and superseded ids |
| `search_media` | Contact sheet of thumbnails with an in-panel lightbox |
| `get_media` | Specimen sheet with image, caption, OCR text, and tags |
| `present_resource` | Display stand that embeds the file, media, or memory viewer |

Every panel provides loading, empty, error, and success states. Tool result
`data` carries the bounded, UI-only excerpts and viewer URLs that make these
panels possible; provider-facing tool content is unchanged.

The dock, panel/expanded surfaces, inspector panels, and folder board are
implemented in the current release, and the committed `frontend/dist` is the
rebuilt production client. Rebuild and commit `frontend/dist` after further
frontend changes, because the Docker image serves the committed client and does
not run a frontend build.

### Resource viewer

`/viewer/file/:fileId`, `/viewer/media/:mediaId`, and
`/viewer/memory/:memoryId` are standalone routes outside `AppShell`; they own
their top bar and safe-area layout so a resource can open in a new tab.

| Resource | Renderer |
|---|---|
| PDF | `react-pdf` 11 + bundled `pdfjs-dist` 6, page navigation, zoom, fit width, text layer |
| DOCX | `docx-preview` inside a script-disabled sandbox |
| Image | native image with zoom/pan, plus a `yet-another-react-lightbox` gallery |
| Text / JSON / Markdown / CSV | archive sheet with wrap/copy/download, pretty JSON, GFM Markdown |
| Memory | pressed-record memory leaf with lineage and trace link |

`GET /api/v1/files/{file_id}/content` serves originals inline with `nosniff`, a
sandboxing CSP, ETag/Last-Modified, and single-range HTTP Range support
(`206`/`416`; `If-None-Match` returns `304`). `/download` stays an attachment.
Text-only records have `has_original=false`; the sheet skips the `/content`
probe entirely and reads indexed chunks.

PDF.js CMaps and standard fonts are copied from the pinned `pdfjs-dist` package
into `frontend/public/pdfjs/` by `bun run pdf-assets`, which `dev` and `build`
run automatically. Vite emits them into `frontend/dist/pdfjs/`; because the
Docker image copies the committed `frontend/dist` and does not run a frontend
build, those emitted assets must be committed with the rest of `dist/`. They are
served locally and never fetched from a CDN.

### Account and sessions

On the first visit the app asks you to create the single owner account. There is
no default password, no email recovery, and no second account. Passwords are
hashed with Argon2; the database stores only a SHA-256 hash of each session
token. The cookie is HttpOnly, SameSite=Lax, and Secure when
`DENDRO_COOKIE_SECURE=true` (the Cloudflare compose sets it).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/auth/status` | First-run state and current session |
| `POST` | `/api/v1/auth/setup` | Create the owner account (first run only) |
| `POST` | `/api/v1/auth/login` | Verify a password and set the session cookie |
| `POST` | `/api/v1/auth/logout` | Delete the session and clear the cookie |
| `GET` | `/api/v1/auth/me` | Current owner (requires a session) |

Every knowledge, media, settings, and agent endpoint requires the session; only
`/api/v1/health`, `/health`, `/api/v1/auth/*`, `/docs`, `/redoc`,
`/openapi.json`, and the SPA shell are public. Tool endpoints need the session
cookie too.

Standalone media API:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/media` | Upload an image; vision caption/OCR when configured |
| `GET` | `/api/v1/media` | List current media |
| `GET` | `/api/v1/media/search?query=` | Text → image over caption/OCR/tags |
| `POST` | `/api/v1/media/search/image` | Image → image visual similarity |
| `GET` | `/api/v1/media/{media_id}/content` | Original image bytes |
| `POST` | `/api/v1/media/{media_id}/describe` | Re-run AI caption/OCR |
| `DELETE` | `/api/v1/media/{media_id}` | Soft-delete the media asset |

Document intake (`POST /api/v1/files`) supports:

- **Images** (`jpg`, `jpeg`, `png`, `webp`) — DeepSeek vision caption + OCR.
- **PDF** — pypdf text first; when the text is empty, garbled, or the AI
  structured analysis says `use_vision`, render up to 10 pages with pypdfium2
  and run vision OCR.
- **DOCX** — python-docx paragraphs and tables; embedded images can provide a
  vision fallback.
- **TXT / MD / CSV / JSON / LOG** — direct text plus AI structured metadata
  (title, summary, tags, document_type).

The same intake is available asynchronously through
`POST /api/v1/files/async` and `POST /api/v1/files/text/async`; poll
`GET /api/v1/files/ingest-jobs/{id}` for stage and chunk progress. See
**Ingestion runtime** above.

Interactive docs: <http://127.0.0.1:8000/docs>. The OpenAPI schema is the source
for the committed Orval client.

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
The committed client includes the folder, move, and copy operations, the
page-context request/detail/entry-kind contracts, agent runtime settings,
conversation compact/clear operations, saved-question CRUD/ask operations, and
the async ingest-job and ingestion-settings operations; the library board,
settings panel, question book, and chat desk call the generated hooks directly.

### Load a real corpus

The Wikipedia loader exercises the same ingestion path as the UI:

```bash
cd backend
uv run python -m script.ingest_wikipedia \
  --lang en --titles Automobile Dendrochronology \
  --prefix /wikipedia/en
```

Ask a question across the imported corpus:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Who built the first practical automobile?","result_number":5}' | jq
```

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

## How retrieval works

1. **Normalize** with NFKC and lower-case. Punctuation becomes whitespace.
2. **Index** overlapping CJK bigrams, Latin words, and Latin trigrams. Each chunk
   stores a unique n-gram list with term frequencies.
3. **BM25** scores candidates (`k1=1.2`, `b=0.75`). A union query such as
   `automobile ford` naturally favours chunks that contain both terms.
4. **Vector recall** uses a 384-dimensional signed feature-hashing embedder by
   default, so it works offline. Set `DENDRO_EMBEDDING_PROVIDER=openai` and the
   matching base URL/model to use a hosted embedding model instead.
5. **Fuse** with reciprocal rank fusion. Each source kind keeps its own top
   `result_number`, so a summary cannot be crowded out by file chunks.
6. **Deduplicate** by chunk id, then hydrate the file, memory, or summary row.
7. **Expand on ask.** `/ask` first asks DeepSeek for 2–4 short retrieval queries,
   runs hybrid search for each, and fuses the runs with another RRF pass. This
   finds the passage that answers a full question instead of only the passages
   that repeat its nouns.

If vector recall is unavailable, search still returns BM25 results. Synchronous
ingestion keeps a chunk text-only when its embedding call fails within the
retry budget; the durable worker treats an exhausted embedding retry as a job
failure, so no partial file is published.

### Do I need an embedding model key?

No. The default signed feature-hashing embedder runs offline and gives real
lexical vector recall. BM25 over CJK bigrams handles exact terms and names. If
you want semantic or cross-lingual recall, point the service at an
OpenAI-compatible embedding endpoint:

```bash
mkdir -p .secrets
cat > .secrets/openai.env <<'EOF'
DENDRO_EMBEDDING_PROVIDER=openai
DENDRO_EMBEDDING_BASE_URL=https://api.openai.com/v1
DENDRO_EMBEDDING_MODEL=text-embedding-3-small
DENDRO_EMBEDDING_DIMENSION=1536
DENDRO_EMBEDDING_API_KEY=sk-...
EOF
chmod 755 .secrets
chmod 644 .secrets/openai.env
```

The Settings page can also store this configuration in the database. After
changing the embedding model, open Settings and run **Re-embed library** (or call
`POST /api/v1/settings/ai/embedding/reindex`) so existing chunks get vectors in
the new dimension. Until then, text search still works and vector search skips
the incompatible chunks.

### What is a signed hashing embedder?

It is a deterministic feature-hashing vectorizer, not a trained neural model.
Each token (a CJK bigram, a Latin word, or a Latin trigram) is hashed with
BLAKE2b into one of 384 buckets. One bit of the digest becomes the sign, so
collisions partially cancel instead of always adding up. The bucket values are
accumulated and the vector is L2-normalized.

```text
token -> BLAKE2b -> bucket 0..383 + sign(+1/-1) -> accumulate -> normalize
```

Consequences:

- **No model download, no GPU, no key.** It runs on the CPU in microseconds per
  chunk and needs only a few kilobytes of RAM per vector.
- **Lexical, not semantic.** `car` and `automobile` are different tokens. BM25
  handles exact terms; DeepSeek query expansion supplies related retrieval
  terms for `/ask`.
- **Deterministic.** The same text always produces the same vector, which makes
  ingestion and tests reproducible.
- **Exact scan at personal scale.** The current implementation scans up to
  20,000 current vectors and computes cosine in Python. At a larger corpus,
  replace it with pgvector/HNSW or a hosted embedding model; the
  `EmbedderProtocol` boundary stays the same.


## Data model

The schema follows one rule: source metadata lives in its owning table, and the
unified chunk table stores only the source key.

```text
file ─────────────┐
tree_node ────────┤
memory ───────────┼──> chunk ──> chunk_ngram
memory_summary ───┘
```

- `file`: one row per version. `is_current` and `deleted_at` are soft state;
  ids are never reused.
- `tree_node`: folders and file leaves in one tree; `superseded_by_id` links a
  hidden branch to its replacement.
- `chunk`: `(source_kind, source_id, chunk_index)` with an optional JSONB vector.
- `chunk_ngram`: the inverted index used by BM25.
- `memory`: linear timeline with `supersedes_ids`, `superseded_by_id`, and
  `status=active|deprecated`.
- `memory_summary`: period, source memory ids, themes, generator, and model.
- `ai_provider_config`: one row per purpose (`chat` / `embedding`), with an
  encrypted API key, a safe hint, and the active model/base URL/dimension.
- `media_asset` / `media_ngram`: the standalone visual archive, its OCR/caption
  text, and the n-gram index used for text → image search.
- `agent_conversation` / `agent_entry` / `agent_run`: the persistent agent's
  transcript scope, immutable entry log, and per-submission run state.
  `agent_commit_seq` groups entries written in one transaction. Page snapshots
  are `pi.page-context` entries in the same log, not a separate table.
- `agent_config`: one row (`id=1`) with the validated runtime limits used by the
  agent loop and the settings API.
- `saved_question`: the Q&A library. `question` is owner-authored; `answer`,
  `citations`, `conversation_id`, and the run status/error fields are written
  only by an ask. `conversation_id` uses `ON DELETE SET NULL`, and
  `last_asked_at` records the most recent attempt.
- `file_ingest_job`: the durable intake queue. It stores the source kind, path,
  payload key, status/stage, `progress_pct`, chunk counts, bounded error fields,
  and attempt/timestamps. A path can have only one active job. The job points at
  its staged file, clears that link on failure, and the file and chunks become
  current only when the job publishes them.
- `ingest_config`: one row (`id=1`) with the validated worker poll, extraction,
  in-flight, embedding, and chunk-size settings. It is not a chunk source; the
  queue references the file that is eventually published.

The complete local design notes live under `docs/plan/` (gitignored). The
committed code, comments, UI copy, and documentation are English.

## Development checks

```bash
# Backend
cd backend
uv run ruff check .
uv run mypy app
PYTHONUTF8=1 uv run bandit -r app -c pyproject.toml
uv run pip-audit
PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/dendromatrix-pytest.log

# Frontend
cd frontend
bun run lint
bun run typecheck
bun run build
bun audit
```

The integration suite uses one real PostgreSQL test database
(`dendromatrix_test`) on the same instance, runs sequentially, and resets every
table between tests. There are exactly ten tests; each one exercises the real
HTTP surface and database. The agent test covers runtime settings defaults,
full PUT/reset, validation, the runtime snapshot used by later runs, auto and
manual compaction, clear, page-context reattachment at a boundary, retry,
parallel/sequential tool execution, and the saved-question library. The
saved-question coverage includes create/list/pagination, ask success, a failed
ask that keeps the row, edit clearing the answer, delete, not-found errors, and
the `conversation_id` `ON DELETE SET NULL` behavior. Page-context
deduplication and ordering, and folder creation plus move/copy coverage, extend
existing tests rather than adding new functions.

The latest migration is `d4b8e6f1a2c7`, after `d1e2f3a4b5c6`. The migrations
after `agent_config` on this branch are:

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
  overlap rule, and seeds row `1`.

Earlier, `e7a1c4b9d2f6` created the singleton `agent_config` table and seeded
row `1`. The integration suite builds tables from SQLAlchemy metadata, so
migration upgrade/downgrade is validated separately against the development
database.

## Project layout

```text
backend/
  app/
    main.py                     API assembly, lifespan, gzip, SPA mount
    worker.py                   dedicated durable-ingestion process
    shared/                     error registry and list envelope
    infrastructure/             config, database, cache, embeddings, AI, files
    module/knowledge/
      domain/                   chunking, n-grams, BM25 terms, timeline, summary
      model/                    SQLAlchemy models incl. ingest jobs/config
      repository/               persistence, retrieval, and job-queue queries
      service/                  orchestration, indexing, ingest jobs/settings
      router/                   HTTP adapters incl. file intake and settings
      schema/                   Pydantic contracts
      exception/                stable error codes
    module/media/               standalone image archive and visual retrieval
    module/agent/               transcript, runtime settings, compaction, tools,
                                saved questions, SSE
  alembic/                      migrations
  tests/                        ten integration tests
frontend/
  src/app/
    component/                  shared archive UI
    generated-apis-types/       committed Orval client
    agent/                      global dock, page capture, inspector panels
    chat/                       reading room, retry, context actions
    questions/                  saved-question Q&A library
    settings/                   provider, agent, and ingestion runtime panels
    viewer/                     file, media, and memory viewers
    library/                    folder workspace board, list, intake progress
    home/ search/ timeline/ tree/ media/ memory/ ask/ ...
  src/apis/fetch-client.ts      the only JSON mutator
  src/apis/agent-stream.ts      SSE transport for agent turns
  src/lib/                      formatting and safe highlighting
  src/styles/                   paper / night archive tokens
  scripts/copy-pdfjs-assets.mjs copies pinned PDF.js CMaps/fonts
  dist/                         committed production build served by FastAPI
docker-compose.yml              normal deployment
docker-compose.dev.yml          local dependencies
docker-compose.cloudflare-tunnel.yml   Cloudflare Tunnel deployment
docs/cloudflare-tunnel.md       Tunnel deployment, backup, and security guide
docker/caddy/                   non-root reverse proxy for the tunnel
```

## Security and privacy

- One owner account protects the archive. Passwords are hashed with Argon2;
  session tokens are stored only as SHA-256 hashes in `user_session`. The cookie
  is HttpOnly, SameSite=Lax, and Secure when `DENDRO_COOKIE_SECURE=true`.
- The normal Compose file binds the API to `127.0.0.1`; the Cloudflare file
  publishes no host port. Login throttling is in-memory and therefore
  single-process.
- Paths reject traversal segments, backslashes, control characters, and
  over-long values. Uploads are capped at 10 MB and restricted to an extension
  allowlist.
- HTML from files and memories is rendered as text through React. Agent Markdown
  uses `skipHtml`; DOCX previews run in a script-disabled sandbox. The UI never
  uses `dangerouslySetInnerHTML`.
- The DeepSeek key lives in `.secrets/deepseek.env` or the environment. It is
  never logged, returned, or committed. Keys saved from the Settings page are
  encrypted in PostgreSQL and returned only as a four-character hint.
- AI calls happen for summaries, `POST /ask`, and agent turns. If the provider
  fails, the API returns a stable error instead of inventing an answer.

## License

MIT. See `LICENSE`.
