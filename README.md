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
> Pi-shaped agent, SSE chat, dedicated PDF/DOCX/image/text viewers, a folder
> workspace, and a three-state agent dock.

## Highlights

- **Files have lineage.** A path is a branch, not an overwrite. Re-uploading a
  file grows a new leaf; the previous edition remains addressable as history.
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
- **Memories are linear and traceable.** A new belief can supersede an old one.
  The old memory leaves the search surface but stays readable through its chain.
- **Search is hybrid.** BM25 over CJK bigrams and Latin tokens runs beside vector
  recall. Results are de-duplicated and fused, with the reason recorded.
- **Time is sampled honestly.** A timeline returns up to five anchors per event
  kind and reports exactly how many events were skipped.
- **AI answers are grounded.** DeepSeek receives retrieved passages, not the
  whole library, and every claim must carry a citation. Without a key, the
  answer endpoint fails closed.
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

Settings API:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/settings/ai` | Both provider slots, masked hints, source, reindex advice |
| `PUT` | `/api/v1/settings/ai/{purpose}` | Create/update `chat` or `embedding` |
| `POST` | `/api/v1/settings/ai/{purpose}/test` | One small provider request + latency |
| `DELETE` | `/api/v1/settings/ai/{purpose}/key` | Remove the stored key |
| `POST` | `/api/v1/settings/ai/embedding/reindex` | Re-embed every current chunk with the active provider |

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

The Cloudflare variant publishes no host port. `cloudflared` connects to a
non-root Caddy reverse proxy, which forwards to the API.

```bash
mkdir -p secrets
# Write the tunnel token; no trailing newline.
printf '%s' 'your-tunnel-token' > secrets/cf_token.txt
chmod 644 secrets/cf_token.txt
export DENDRO_PUBLIC_HOST=archive.example.com
docker compose -f docker-compose.cloudflare.yml up -d --build
```

Point the tunnel ingress for `archive.example.com` at `http://caddy:80`. The
token file is gitignored. See `secrets/README.md` for permissions.

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
`chunk_range=1`, `day_range=1`, `path_depth=1`, and `memory_range=0`. The agent's
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
| `POST` | `/api/v1/agent/conversations/{conversation_id}/messages` | Append a user entry and run the loop |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/retry` | Retry the latest failed/cancelled run |
| `GET` | `/api/v1/agent/tools` | Current tool catalog plus prompt/tools versions |

`POST /api/v1/agent/conversations/{conversation_id}/messages` accepts
`{content, request_id?, page_context?}` and `.../retry` accepts
`{request_id?}`. Both stream `text/event-stream` by default. The event names are
`run_start`, `message_start`, `message_delta`, `message_end`, `tool_start`,
`tool_end`, `run_end`, and `error`. `run_start` reports
`page_context_entry_id` (or `null`) and `page_context_attached` so the client can
mark whether a new snapshot was written. `tool_end` carries the persisted
tool-result `data` payload plus `duration_ms` and `error_code`, so the inspector
can render previews before the transcript refetch settles. `message_start` has
`entry_id=null` because the assistant entry is persisted only at `message_end`;
deltas are transport-only. Send `Accept: application/json` for the completed turn
instead. SSE responses set `Cache-Control: no-cache, no-transform` and
`X-Accel-Buffering: no`, and Starlette's GZip middleware excludes
`text/event-stream`.

The agent allows one active run per conversation, at most 8 model steps, 6 tool
calls per user turn, 24k tokens, and 12k result characters per tool (24k total).
A failed or cancelled run can be retried without duplicating the user entry. The
backend retry endpoint is tested; the chat UI does not yet render a Retry action.
Conversation detail returns the first entry page, and the UI loads later pages
with **Load more entries**. It also returns `last_page_context_key`, read from the
entry log rather than from browser storage, so a reloaded conversation still
knows which page snapshot was attached last.

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

- `begin_message` compares the incoming key with the newest existing
  `pi.page-context` entry in the same conversation.
- Only a different key appends a new snapshot. Asking again from the same page
  does not repeat it.
- The snapshot entry and the user entry share one `commit_seq`; the snapshot is
  ordered immediately before the user entry.
- Earlier entries are never rewritten, so the stable system/tool prefix and the
  previous conversation prefix remain a valid KV-cache lineage.

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

### Chat reading room

`/chat` and `/chat/:conversationId` are the persistent reading room for the
agent. The thread rail lists active and archived conversations and supports
rename, archive/restore, delete, and a new thread; the sheet renders immutable
entries as keeper marginalia, archive sheets, field-note tool results, and
structured resource cards. The composer streams over SSE, supports
Cmd/Ctrl+Enter and a stop action, and refreshes the thread list plus the active
transcript when the run settles (other conversations are not refetched).

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
The committed client includes the folder, move, and copy operations and the
page-context request, detail, and entry-kind contracts; the library board calls
the generated hooks directly.

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

If vector recall is unavailable, search still returns BM25 results. If an
embedding call fails during ingestion, the chunk is stored text-only.

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
HTTP surface and database. Page-context deduplication and ordering extend the
existing agent test, and folder creation plus move/copy coverage extend the
existing file-library test. Neither adds an eleventh test function.

Current validation: `ruff`, `mypy`, `bandit`, `pip-audit`, and the ten
sequential tests pass. Migration `c4f1a9e2b7d3` upgrades and downgrades on the
real development database. Frontend typecheck, lint, build, and audit pass.
Playwright passed 34 deterministic checks plus a 6-check focused re-check,
including the `save_memory` receipt panel. A clean Docker Compose smoke passed
once.

## Project layout

```text
backend/
  app/
    main.py                     API assembly, lifespan, gzip, SPA mount
    shared/                     error registry and list envelope
    infrastructure/             config, database, cache, embeddings, AI, files
    module/knowledge/
      domain/                   chunking, n-grams, BM25 terms, timeline, summary
      model/                    SQLAlchemy models
      repository/               persistence and retrieval queries
      service/                  orchestration and indexing
      router/                   HTTP adapters
      schema/                   Pydantic contracts
      exception/                stable error codes
    module/media/               standalone image archive and visual retrieval
    module/agent/               persistent transcript, page context, tools, SSE
  alembic/                      migrations
  tests/                        ten integration tests
frontend/
  src/app/
    component/                  shared archive UI
    generated-apis-types/       committed Orval client
    agent/                      global dock, page capture, inspector panels
    chat/                       persistent reading room
    viewer/                     file, media, and memory viewers
    library/                    folder workspace board and list
    home/ search/ timeline/ tree/ media/ memory/ ask/ ...
  src/apis/fetch-client.ts      the only JSON mutator
  src/apis/agent-stream.ts      SSE transport for agent turns
  src/lib/                      formatting and safe highlighting
  src/styles/                   paper / night archive tokens
  scripts/copy-pdfjs-assets.mjs copies pinned PDF.js CMaps/fonts
  dist/                         committed production build served by FastAPI
docker-compose.yml              normal deployment
docker-compose.dev.yml          local dependencies
docker-compose.cloudflare.yml   tunnel deployment
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
