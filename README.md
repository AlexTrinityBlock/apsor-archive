<div align="center">
  <img src="frontend/public/favicon.svg" alt="Apsor Archive" width="112" height="112">
</div>

<h1 align="center">Apsor Archive</h1>

<p align="center">
  A local-first, private knowledge and memory archive for a family or small team.
</p>

<p align="center">
  <a href="https://github.com/AlexTrinityBlock/apsor-archive"><img src="https://img.shields.io/badge/version-0.1.0-171717" alt="Version 0.1.0"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/AlexTrinityBlock/apsor-archive?label=license&amp;color=171717" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/self--hosted-yes-171717" alt="Self-hosted">
  <a href="https://github.com/AlexTrinityBlock/apsor-archive/pulls"><img src="https://img.shields.io/badge/PRs-welcome-171717" alt="Pull requests welcome"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&amp;logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/react-19-61DAFB?logo=react&amp;logoColor=black" alt="React 19">
  <img src="https://img.shields.io/badge/vite-8-646CFF?logo=vite&amp;logoColor=white" alt="Vite 8">
  <img src="https://img.shields.io/badge/bun-1.3.6-fbf0df?logo=bun&amp;logoColor=black" alt="Bun 1.3.6">
  <img src="https://img.shields.io/badge/postgresql-17-4169E1?logo=postgresql&amp;logoColor=white" alt="PostgreSQL 17">
  <img src="https://img.shields.io/badge/docker%20compose-2496ED?logo=docker&amp;logoColor=white" alt="Docker Compose">
</p>

**English** · [繁體中文](README.zh-TW.md) · [简体中文](README.zh-CN.md)

## Table of contents

- [Highlights](#highlights)
- [Stack](#stack)
- [Quick start](#quick-start)
  - [Docker Compose (normal)](#docker-compose-normal)
  - [Object storage (local or R2)](#object-storage-local-or-r2)
  - [Configure providers in the app](#configure-providers-in-the-app)
  - [Web research tools](#web-research-tools)
  - [Frequently used prompts](#frequently-used-prompts)
  - [Agent runtime settings](#agent-runtime-settings)
  - [Ingestion runtime](#ingestion-runtime)
  - [Local development](#local-development)
  - [Cloudflare Tunnel](#cloudflare-tunnel)
- [Tool surface](#tool-surface)
  - [Folder workspace](#folder-workspace)
  - [Agent conversations](#agent-conversations)
  - [Saved questions](#saved-questions)
  - [Chat reading room](#chat-reading-room)
  - [Chat workspace](#chat-workspace)
  - [Resource preview](#resource-preview)
  - [Accounts, roles, and sessions](#accounts-roles-and-sessions)
  - [Generated API client and drift](#generated-api-client-and-drift)
  - [Load a real corpus](#load-a-real-corpus)
  - [Long-document validation](#long-document-validation)
- [How retrieval works](#how-retrieval-works)
  - [Do I need an embedding model key?](#do-i-need-an-embedding-model-key)
  - [What is a signed hashing embedder?](#what-is-a-signed-hashing-embedder)
- [Data model](#data-model)
- [Development checks](#development-checks)
- [Project layout](#project-layout)
- [Security and privacy](#security-and-privacy)
- [License](#license)

A local-first knowledge and memory archive with a branching file library, a
linear memory timeline, hybrid retrieval, and grounded AI answers. Each account
has its own private archive; one root account manages membership and shared
runtime settings.

Apsor Archive is not a note list. It is a retrieval surface designed for a small
number of deliberate tool calls: search a passage, read its neighbours, walk the
path, sample a season, press a new memory, or trace a superseded one. Every
result carries its source, chunk number, and time.

> Status: v0.1.0 — file/memory archive, root plus per-user accounts, persistent
> Pi-shaped agent with database-backed runtime limits, compaction, parallel
> tools, SSE chat, a saved-question Q&A library, durable async ingestion,
> dedicated PDF/DOCX/image/text preview engines, a folder workspace, and a
> three-panel chat workspace.

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
- **The agent has one workspace.** Chat is a three-panel desk: a collapsible
  conversation drawer, the streaming transcript, and a tool inspector with a
  draggable, persisted split. There is no second composer or command palette.
- **Agent limits are database-backed.** The model context window, compaction
  threshold, step and tool caps, parallel width, and result budgets live in one
  validated `agent_config` row and apply to new runs without a restart. The
  context window is model metadata; compaction is the long-conversation control.
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
  whole library, and every claim must carry a citation. Without a key, agent
  turns fail closed.
- **Questions outlive the conversation.** Save a question before you have an
  answer, ask it later, and keep the answer, its citations, the run status, and
  a link to the conversation on the same row. Editing the question clears the
  stale answer instead of leaving a mismatched pair on screen.
- **Images live in the File Library.** An image is a normal file record with its
  original bytes, path, and chunks. A vision-capable chat provider adds OCR and
  caption metadata; without one, a filename-derived caption keeps local uploads
  searchable. There is no separate image index.
- **Documents choose their extractor.** PDFs try text first and fall back to
  vision for scanned pages. DOCX, TXT, JSON, CSV, and logs use text, with AI
  structured metadata; images use vision or the filename fallback.
- **The interface speaks three languages.** English, Traditional Chinese, and
  Simplified Chinese can be switched from the Settings page. The choice is
  stored per browser and applies to the whole interface, never to archive
  content.
- **The archive is private, multi-account, and local-first.** One root account
  manages accounts and global runtime settings; every other account gets a
  private archive of files, folders, chunks, memories, summaries, conversations,
  entries, runs, approvals, saved questions, prompts, and profile cards.
  PostgreSQL row-level security enforces ownership on every private table, so a
  missing query filter cannot expose another person's archive. Passwords use
  Argon2 and sessions use HttpOnly cookies. Run it on your own machine; put it
  behind Cloudflare Tunnel only with your own access controls.
- **Original bytes can live in Cloudflare R2.** `APSOR_STORAGE_BACKEND=local|r2`
  selects where new originals are written. Reads follow the backend recorded on
  each row, so a staged migration can serve a mixed archive. The R2 bucket is
  private and the app never issues presigned or public URLs.

## Stack

| Layer | Choice |
|---|---|
| API | Python 3.13, FastAPI, SQLAlchemy 2 async, Alembic, psycopg 3 |
| Storage | PostgreSQL 17 (`pg_trgm` for path fuzzy search); original bytes on local disk or in private Cloudflare R2 |
| Cache | Valkey / Redis-compatible, with a memory fallback |
| Retrieval | CJK bigram + Latin token n-grams, BM25, signed hashing vectors, RRF |
| AI | DeepSeek `deepseek-flash` (OpenAI-compatible chat completions) |
| Frontend | React 19, TypeScript, Vite, React Router, React Query, Orval |
| Deploy | Docker Compose, optional Cloudflare Tunnel, or bare metal with `uv` |

## Quick start

### Docker Compose (normal)

```bash
mkdir -p data
sudo chown -R 10001:10001 data
# The production Compose default is R2; local disk is the simplest first run.
APSOR_STORAGE_BACKEND=local docker compose up --build
```

> Note: `./data` is bind-mounted into the container and the container process
> runs as uid `10001`. Create the directory and fix its owner before the first
> boot, otherwise uploads and original-byte writes fail. If the host user is
> already uid `10001`, the `sudo chown` can be skipped.

Open <http://127.0.0.1:8000>. The first visit asks you to create the root
account. The root can then create normal accounts from **Accounts**; each new
account receives a one-time temporary password and must change it at first
sign-in. PostgreSQL uses a named volume; local original bytes and the generated
secret key live under the host's `./data` directory. The production Compose
files default to `APSOR_STORAGE_BACKEND=r2`; see
[Object storage](#object-storage-local-or-r2) for the credentials it needs, or
keep local storage for a self-contained host.

The `postgres-data` volume is pinned to an explicit physical name:
`apsor-archive_postgres-data` for `docker-compose.yml` and
`apsor-archive-dev_postgres-data` for `docker-compose.dev.yml`, so a Compose
project rename cannot orphan the database. A stack created before this rename
used a different physical volume name, so copy that volume's contents into the
new one (or keep the old name in the local Compose file) before starting.
Otherwise PostgreSQL initialises an empty database.

The Docker build compiles the frontend from `frontend/` in a Bun stage, so
`docker compose up --build` picks up a frontend change without a manual build.
Run `cd frontend && bun run build` only when you want a local preview.

To enable AI answers and AI summaries:

```bash
mkdir -p .secrets
printf 'APSOR_DEEPSEEK_API_KEY=sk-your-key\n' > .secrets/deepseek.env
chmod 755 .secrets
sudo chgrp 10001 .secrets/deepseek.env
chmod 640 .secrets/deepseek.env
docker compose up -d --build
```

The Compose file mounts `.secrets/` read-only. The app reads the env file itself,
so the key never becomes a container environment variable and never appears in
`docker compose config`. The API container runs as uid `10001`, so the file must
be readable by that uid: group `10001` with mode `640`, or `644` on a
single-user host. The key is gitignored and is never returned by the API.
Without it, summaries fall back to a deterministic extractive form, image
uploads use the filename caption, and agent messages return
`503 agent_not_configured`.

### Object storage (local or R2)

`APSOR_STORAGE_BACKEND` chooses the default for new original bytes:

- `local` writes under `APSOR_DATA_DIR` and is the default for development and
  tests.
- `r2` writes to a private Cloudflare R2 bucket. Both production Compose files
  default to `r2`; set `APSOR_STORAGE_BACKEND=local` for a first boot or a
  rollback.

The non-secret R2 values are `APSOR_R2_ENDPOINT_URL`, `APSOR_R2_BUCKET`
(`apsor-archive` in the deployment), `APSOR_R2_REGION` (`auto`), and
`APSOR_R2_PREFIX`. The account endpoint has no default: put
`APSOR_R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com` in a
gitignored `.env` file next to the Compose file, or export it, before running
with the `r2` backend. Credentials live in the gitignored `.secrets/r2.env`,
which Compose mounts read-only and the app reads itself, so they never become
container environment variables:

```bash
mkdir -p .secrets
# Fill these in locally; never commit the file.
printf 'APSOR_R2_ACCESS_KEY_ID=...\nAPSOR_R2_SECRET_ACCESS_KEY=...\n' \
  > .secrets/r2.env
chmod 755 .secrets
# Container uid 10001 needs read access; other host users do not.
sudo chgrp 10001 .secrets/r2.env
chmod 640 .secrets/r2.env
```

The file must be readable by container uid `10001` (mode `640` with group
`10001`, or `644` on a single-user host). The bucket stays private:
no presigned URLs, no public bucket access, and no lifecycle expiry on `files/`.
`data/.secret_key` is the Fernet master key and remains local; back it up
separately from PostgreSQL.

To move an existing archive from local disk to R2, stop the API and worker and
run the storage CLI from `backend/`:

```bash
uv run python -m script.migrate_storage_to_r2 --dry-run
uv run python -m script.migrate_storage_to_r2 --copy
uv run python -m script.migrate_storage_to_r2 --verify
# only after a verified backup and rollback window
uv run python -m script.migrate_storage_to_r2 --delete-local
```

`--copy` uploads and verifies size and SHA-256, then marks the matching `file`
and retryable `file_ingest_job` rows as `storage_backend='r2'`. Keep the
PostgreSQL dump, the data-directory backup, and the R2 bucket contents together
as one backup set. Back up the bucket with versioning or an object-sync job;
soft-deleted files keep their objects.

### Configure providers in the app

The Settings page is the normal way to configure providers, and only the root
account can edit the global registry. It writes to four independent capability
tables, so one capability can never overwrite another:

- **Chat** — `chat_provider_config`: DeepSeek or any OpenAI-compatible chat
  endpoint. Multiple saved rows are allowed; exactly one is active.
- **Embedding** — `embedding_provider_config`: offline `hashing`, `openai`, or
  `openai-compatible`. Multiple saved rows are allowed; exactly one is active.
- **Web search** — `web_search_provider_config`: Tavily today, with a provider
  adapter seam for future search APIs. Multiple saved rows are allowed; exactly
  one is active.
- **Web fetch** — `web_fetch_provider_config`: Tavily `extract` today. Web search
  and web fetch are deliberately separate rows, so they can use different
  providers or different credentials.

Every table has a partial unique index on `is_active`; PostgreSQL enforces at
most one active row per capability. Deleting a row does not reuse its identity
id. Provider rows are global deployment configuration: only the root account can
list, edit, test, or delete them, and normal users never receive a provider
secret or a global runtime setting. The API never returns a plaintext key: the
browser receives only a hint such as `...14f8`. `APSOR_SECRET_KEY` supplies the Fernet master key. If it is unset,
a `0600` key file is created at `data/.secret_key` (or `/data/.secret_key` in
Docker), so encrypted values survive restarts. `APSOR_TAVILY_API_KEY` is an
optional environment fallback for both web capabilities.

Precedence is: **active database row → environment → built-in default**. The
Settings page labels each provider with its source. Changing the embedding model
does not rewrite existing vectors; `reindex_required` warns you. Run **Re-embed
library** (or `POST /api/v1/settings/providers/embedding/reindex`) to refresh
current chunks. Vector search skips chunks whose dimension does not match the
current embedder.

Provider registry API:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/settings/providers` | Four capability groups, masked hints, active row, reindex advice |
| `POST` | `/api/v1/settings/providers/{capability}` | Create one saved provider; optionally activate it |
| `PUT` | `/api/v1/settings/providers/{capability}/{provider_id}` | Replace one saved provider |
| `DELETE` | `/api/v1/settings/providers/{capability}/{provider_id}` | Delete one saved provider |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/activate` | Make it the only active row for that capability |
| `POST` | `/api/v1/settings/providers/{capability}/deactivate` | Clear the active row and fall back to environment/default |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/test` | One small provider request plus latency |
| `POST` | `/api/v1/settings/providers/embedding/reindex` | Re-embed every current chunk with the active provider |

`{capability}` is one of `chat`, `embedding`, `web_search`, or `web_fetch`.
The registry response is cached for 30 seconds under the `providers` cache
scope; every provider write bumps that scope.

### Web research tools

The agent has two read-only tools for external research:

| Tool | What it does |
|---|---|
| `web_search` | Search the public web with the active `web_search` provider; returns title, URL, score, and a bounded excerpt. |
| `web_fetch` | Fetch one public `http(s)` URL with the active `web_fetch` provider and return one server-defined Markdown page. |

Tavily is the first adapter (`/search` and `/extract`). The provider seam is a
protocol, so another search or fetch API can be added without changing the tool
layer. Search results are cached for 15 minutes under the `providers` cache
scope; provider writes invalidate them. `web_fetch` rejects non-HTTP(S),
credentials in the URL, `localhost`/`.local`/`.internal`, and private or
special-use IP literals.

`web_fetch` caches the complete extracted document once per URL for one hour, so
paging never calls the provider again. Its model-facing arguments are only
`url` and `page` (1-based, default 1). The server hard-wraps every source line
at 800 characters and packs whole lines into pages of up to 12,000 characters
(or the configured `web_fetch_max_chars` when smaller, never below 801), so a
page never exceeds its budget and always contains at least one line. There are no line numbers to count
and no offsets to compute: call `page=1`, then `page=2`, and so on until
`has_more=false`. Each result reports `page`/`total_pages`, `page_chars`,
`total_chars`, `has_more`, `next_page`, and `source_truncated`, and the body ends
with a plain-text footer such as:

```text
[web_fetch: page 1/2. More content: call web_fetch again with page=2.]
```

`next_page` is exact whenever `has_more=true`. Concatenating every page covers
the cached document exactly once, with no gaps or overlaps. The normalized full
document is capped at 2,000,000 characters; beyond that it is cut and
`source_truncated=true`, so the final page footer says the source was truncated.
Both tools return XML carrying `provider`, `retrieved_at`, `cached`, and
`truncated`, and the agent is instructed to cite the URL and retrieval time.

A conversation freezes its tool snapshot when it is created, so an older
conversation keeps its previous `web_fetch` schema. The former `offset`,
`limit`, and `max_chars` arguments are still accepted but hidden from the
model-facing schema; they exist only so conversations frozen on
`archive-tools-v4`/`v5` keep validating. Page mode ignores `max_chars` and
`limit`, and a legacy `offset` simply selects the page that contains that line.

Summary search results and timeline summary events are explicitly marked as
compressed views:

```xml
<source kind="summary" id="12" view="compressed" memory_count="37" ...>
  <compressed_view coverage_start="..." coverage_end="..." source_memory_count="37">
    This is a compressed summary of 37 original memories, not the complete original content.
  </compressed_view>
  ...
</source>
```

The agent sees `view="compressed"`, the coverage window, and the original memory
count in the tool result itself, so it does not treat a summary as a full
transcript.

### Frequently used prompts

The **Frequent prompts** panel on `/settings` edits the shortcuts shown on the
empty `/chat` page. The list is private to the signed-in account: each row has a
title, prompt text, and `sort_order`; the list is capped at 20 rows per account,
ordered by `sort_order` then `id`, and cached for 60 seconds under that account's
`prompts` cache scope. Clicking a shortcut fills the composer with its full
prompt text; it does not send the message. The API is
`GET/POST/PUT/DELETE /api/v1/settings/frequent-prompts`.

### Agent runtime settings

The **Agent runtime** panel on `/settings` (root only) edits the singleton
`agent_config` row (`id=1`). Provider and model selection stay in the AI settings
above, so there is still one source of truth for which model answers. All
twelve runtime values are stored in PostgreSQL, apply to new runs without a
restart, and are shared by every account.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/agent/settings` | Effective config, defaults, source, `updated_at` |
| `PUT` | `/api/v1/agent/settings` | Full replacement; all twelve fields are required |
| `POST` | `/api/v1/agent/settings/reset` | Persist and return the built-in defaults |

The generated operations are `getAgentSettings`, `updateAgentSettings`, and
`resetAgentSettings`.

The read shape is `{config, defaults, source, updated_at}`, where `source` is
`database` for a stored row or `default` when the API had to create or repair the
row from defaults. `PUT` requires a complete snapshot: omitted fields and extra
fields are rejected.

| Field | Default | Range |
|---|---|---|
| `compaction_threshold_tokens` | 75,000 | 1,000–200,000; below the context window |
| `context_window_tokens` | 1,000,000 | 8,000–2,000,000; model metadata |
| `max_steps` | 24 | 1–32 |
| `max_tool_calls_per_turn` | 20 | 1–24 |
| `max_parallel_tools` | 6 | 1–24 |
| `max_tool_result_chars` | 100,000 | 1,000–200,000 |
| `max_page_context_chars` | 6,000 | 500–50,000 |
| `max_compaction_summary_chars` | 6,000 | 1,000–20,000 |
| `max_compaction_last_user_chars` | 4,000 | 500–10,000 |
| `auto_compaction_enabled` | `true` | boolean |
| `parallel_tools_enabled` | `true` | boolean |
| `save_memory_requires_approval` | `true` | boolean; manual approval for `save_memory` |

Pydantic and matching PostgreSQL check constraints enforce the ranges and two
cross-field rules: the compaction threshold must stay below the model context
window, and the parallel width must not exceed tool calls per turn. The app's
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
uv run apsor-archive worker
# or
uv run python -m app.worker
# process at most one job, then exit
uv run python -m app.worker --once
```

The standard and Cloudflare Compose stacks run this as a dedicated `worker`
service and set `APSOR_INGEST_WORKER_ENABLED=false` on the API, so exactly one
process owns the queue.

The **Ingestion runtime** panel on `/settings` (root only) edits the singleton
`ingest_config` row. It is a full replacement, not a patch, and the read body
carries `{config, defaults, source, updated_at}` with a Database/Defaults badge.
The worker may claim jobs across accounts, but every parse, chunk, embedding, and
publish step runs in the job owner's row-level-security context.

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

`./start.sh` is the shortest bare-metal path: it starts the dev database/cache
if Docker is available, sources `.secrets/deepseek.env`, syncs the backend, and
serves the API and the built client at <http://127.0.0.1:8000>. Run
`cd frontend && bun run build` once before the first bare-metal start.

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
export APSOR_PUBLIC_HOST=archive.example.com
docker compose -f docker-compose.cloudflare-tunnel.yml up -d --build
```

Point the tunnel ingress for `archive.example.com` at `http://caddy:80`. The
token file is gitignored. Caddy serves only the host named by
`APSOR_PUBLIC_HOST` and answers `404` for every other host, so do not add a
second public hostname to the tunnel ingress. See
`secrets/README.md` for permissions and [`docs/cloudflare-tunnel.md`](docs/cloudflare-tunnel.md) for the
complete English deployment, backup, security, and troubleshooting guide.

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
| `save_memory` | `POST /api/v1/memories` | A new memory with an auto-generated title, the deprecated memories it replaced, and any new summary; omit `content` to deprecate `supersedes` ids without a replacement |
| `read_memory` | `GET /api/v1/memories/{memory_id}?memory_range=1&trace_history=true` | Target, neighbours, supersedes, successor, and chain |

The persistent archive agent exposes nine model tools: the six above plus
`present_resource`, `web_search`, and `web_fetch`. The HTTP examples use
explicit parameters; the HTTP server defaults are `result_number=2`,
`chunk_range=1`, `day_range=1`, `path_depth=1`, and `memory_range=0`. Text is chunked at about 4,000 characters with a 500-character overlap; existing files keep their original chunk boundaries until re-ingested. The agent's
tool schemas choose their own defaults, such as `result_number=8` and
`day_range=7`. For external LLM callers, the separate `/api/v1/tools/*` facade
renders the same services as compact XML; the persistent agent calls the
services directly through its own registry.

`present_resource` returns a resource URL such as `/viewer/file/{id}?chunk={n}`
or `/viewer/memory/{id}` and never fetches the resource. The client redirects
file links into the File Library preview modal and memory links into the memory
reader.

In the chat inspector, `web_search` opens the query, provider, retrieval time,
and every result with a clickable URL, excerpt, and score; `web_fetch` opens the
source metadata and the fetched body. Web result URLs and fetched content have
copy actions. Memory citations display as `Memory: <generated title>` for people
while the model and tooltip keep the stable `[memory:id]`. Memory text, each file
chunk, and the conversation transcript also have one-click copy actions.

Every memory row stores a short auto-generated `title`. On save and edit the
backend asks the configured chat provider for a name before the single insert or
update, so the body and title are stored atomically. If the provider is
unavailable, the first 80 characters of the body become the fallback title. The
chat renders each memory citation as the numeric label plus that name; older
transcripts resolve the missing name on demand through `read_memory`.

`save_memory` has a replacement-free deprecation form: omit `content`, pass the
existing ids in `supersedes`, and optionally include `reason`. The backend marks
those rows deprecated, stamps `deprecated_at`, marks their search chunks
non-current, and writes no new memory. The same call with `content` keeps the
original supersession behavior.

Persisted `pi.tool-result` entries also carry UI-only `data`: bounded excerpts,
dimensions, tags, and viewer URLs for the expanded inspector. This payload never
enters the provider message; the model still sees only the XML tool result.

`save_memory` is a write action. The `save_memory_requires_approval` runtime
setting (default `true`, editable in **Settings → Agent runtime → Tool
execution**) controls how it is authorized:

- **On (default):** the loop does not execute the write. It persists a durable
  `agent_approval` row, appends no tool result yet, moves the run to `waiting`,
  and emits `approval_required` with a bounded preview. A deprecation-only call
  previews the target ids and reason instead of a proposed body. `POST
  /api/v1/agent/approvals/{approval_id}/approve` is the only path that executes
  the write; `.../reject` appends a `memory_rejected` tool result and resumes
  without writing. The model's `user_confirmed` argument is ignored for
  authorization.
- **Off:** no waiting run or approval row is created. The backend authorizes the
  validated write itself (`approved=True` in the tool registry) and the call
  completes in the same turn. Model-supplied `user_confirmed` still never
  authorizes a write.

Duplicate or stale resolutions return `409 agent_approval_not_pending`, and
archived or deleted conversations fail closed. Disabling the setting does not
approve or cancel approvals that already exist; they remain explicit pending
rows and their cards keep rendering. The expanded inspector still renders the
resulting receipt after a write.

Additional surfaces: `POST /api/v1/files` (multimodal intake), `POST
/api/v1/files/text`, `DELETE /api/v1/files/{file_id}`, `GET /api/v1/paths`,
`GET /api/v1/memories`, `POST /api/v1/memories`,
`PATCH /api/v1/memories/{memory_id}` (edit text; the title is regenerated),
`POST /api/v1/memories/{memory_id}/deprecate` (retire directly with an optional
`reason`), `POST /api/v1/summaries`, `GET /api/v1/stats`,
`GET /api/v1/health`, and `GET /api/v1/ai/status`.

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
  bytes. Only `raw_file_path` and the file name change, so existing search,
  timeline, citation, and viewer links remain valid.
- A **copy** creates a new current file id at version 1, clones the stored
  original when one exists, rebuilds chunks and embeddings, and copies the AI
  summary, tags, document type, and extraction method. Both files remain
  current and searchable.
- Moves and copies must keep the original extension. A target occupied by
  another folder or current file returns `409 tree_path_conflict`; an invalid
  path or a changed extension returns `422 invalid_path`.

| Method | Path | Body | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/folders` | `{path}` | Create a folder and missing ancestors; idempotent `201` |
| `POST` | `/api/v1/files/{file_id}/move` | `{path}` | Move one current file in place; `200` |
| `POST` | `/api/v1/files/{file_id}/copy` | `{path}` | Copy one current file to a new record; `201` |

All three endpoints require an authenticated account and operate only on that
account's folder tree. They bump that account's archive cache version when they
change the folder or file index; a path in another account is a separate,
non-conflicting tree.

### Agent conversations

`/api/v1/agent` is a persistent, Pi-shaped multi-turn archive agent. The term
refers to the durable-transcript model of the Pi coding-agent harness: a
conversation is an append-only log of immutable entries, and the provider
context is rebuilt from that log after the newest reset or compaction boundary
rather than from a mutable chat array. Apsor Archive implements the model in
Python and PostgreSQL; it does not run the Pi runtime or depend on its packages.
The tables are:

- `agent_conversation` — transcript scope, provider/model identity, and metadata.
- `agent_entry` — immutable `pi.user`, `pi.assistant`, `pi.tool-result`,
  `pi.page-context`, `pi.system`, `pi.reset`, `pi.compaction`, and `ui.notice`
  entries. `model` is exactly the provider payload; `data` is UI/diagnostics
  only.
- `agent_run` — durable state for one submission (`request_id`, status, abort,
  last entry, safe error). `agent_commit_seq` groups entries written in one
  transaction.
- `agent_approval` — one durable pending/approved/rejected/expired human decision
  for a confirmation-required tool call, including validated arguments, a safe
  preview, and the loop snapshot used to resume the waiting run.
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
| `POST` | `/api/v1/agent/conversations/{conversation_id}/fork` | Copy entries through an inclusive cutoff into a new thread |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/messages` | Append a user entry and run the loop |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/retry` | Retry the latest failed/cancelled run |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/approvals?status=` | Durable approvals, oldest first (default `pending`) |
| `POST` | `/api/v1/agent/approvals/{approval_id}/approve` | Execute once, append the tool result, resume |
| `POST` | `/api/v1/agent/approvals/{approval_id}/reject` | Append `memory_rejected`, resume without writing |
| `GET` | `/api/v1/agent/tools` | Current tool catalog plus prompt/tools versions |
| `GET` | `/api/v1/agent/settings/system-prompt` | List every system prompt section |
| `POST` | `/api/v1/agent/settings/system-prompt` | Create one section (`201`) |
| `PUT` | `/api/v1/agent/settings/system-prompt/order` | Reorder every section |
| `PUT` | `/api/v1/agent/settings/system-prompt/{section_id}` | Replace one section |
| `DELETE` | `/api/v1/agent/settings/system-prompt/{section_id}` | Delete one section (`204`) |
| `POST` | `/api/v1/agent/settings/system-prompt/reset` | Replace every section with the four seeded defaults |

`POST /api/v1/agent/conversations/{conversation_id}/messages` accepts
`{content, request_id?, page_context?, client_timezone?,
client_utc_offset_minutes?}` and `.../retry` accepts `{request_id?}`. Both stream
`text/event-stream` by default. The client timezone is stored with a
server-rendered `<current_time>` block on each user entry; the block is appended
after the message text exactly once. The ordered system prompt sections are
written at conversation creation and frozen into that thread. The four defaults
are seeded as ordinary rows; Settings lets the root account edit, delete, or
reorder every row for the whole deployment. The event names are
`run_start`, `message_start`, `message_delta`, `message_end`, `tool_start`,
`tool_end`, `approval_required`, `run_end`, and `error`. `run_start` reports
`page_context_entry_id` (or `null`), `page_context_attached`, and `resumed` so
the client can mark whether a new snapshot was written and whether the stream
continues a durable waiting run. `tool_start` and `tool_end` also carry
`parallel`, `batch_size`, and `parallel_index` for the assistant call batch.
`tool_end` carries the persisted tool-result `data` payload plus `duration_ms`
and `error_code`, so the inspector can render previews before the transcript
refetch settles. `message_start` has `entry_id=null` because the assistant entry
is persisted only at `message_end`; deltas are transport-only. Send
`Accept: application/json` for the completed turn instead. SSE responses set
`Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`, and
Starlette's GZip middleware excludes `text/event-stream`.

Each conversation allows one active run at a time. The defaults allow 24 model
steps, 20 tool calls per user turn, 6 parallel tools, 75,000 tokens of active
context before auto compaction, and 100,000 result characters per tool. There is
no cumulative per-turn token ceiling; a turn ends only on a final answer, the
step or tool-call limits, a user cancellation, or a provider failure. The
1,000,000-token context window records provider capacity and is the bound the
compaction threshold is measured against. Each
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
retry can hit the same context limit again if the transcript is still
too long. The endpoint returns `409 agent_run_not_retryable` when the latest run
is completed or otherwise not failed/cancelled; the UI refetches the transcript
after that error so a stale Retry action disappears.

#### Human approval for `save_memory`

With `save_memory_requires_approval=true` (the default), a valid confirmation
call never writes from the model loop. It persists `agent_approval` with the
conversation, run, tool-call id, validated arguments, a safe preview, and a
resume snapshot; safe calls in the same batch still run and their results are
appended. The run becomes `waiting`, the SSE stream ends with
`approval_required` plus `run_end {status: "waiting"}`, and the assistant tool
call remains in the transcript. A batch with multiple confirmation calls creates
one approval per call; resolutions must follow approval id order, and the loop
resumes after the last pending row is resolved.

With the setting off, the validated call executes immediately with backend
authorization (`approved=True`), no `agent_approval` row is created, and the run
completes normally. The model's `user_confirmed` argument never authorizes a
write in either mode. Turning the setting off does not resolve approvals that
already exist; their cards remain and need an explicit decision.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/agent/conversations/{id}/approvals?status=pending` | Pending approvals, oldest first |
| `POST` | `/api/v1/agent/approvals/{approval_id}/approve` | Execute once, append the result, resume |
| `POST` | `/api/v1/agent/approvals/{approval_id}/reject` | Append `memory_rejected`, resume without writing |

Both resolution endpoints accept `Accept: application/json` or stream the
resumed turn as SSE. They begin with `run_start {resumed: true}`, then a
`tool_end` for the resolved result; if another approval remains they end with
`approval_required` and `run_end {status: "waiting"}`, otherwise the normal loop
continues. Approving after the row is resolved, expired, or orphaned returns
`409 agent_approval_not_pending`; an archived conversation returns `409
agent_conversation_archived`.

On API restart, stale `running` runs fail with `interrupted`. A `waiting` run
with a valid pending approval survives and remains visible from the approvals
endpoint. A waiting run without a valid pending approval fails closed with
`approval_orphaned`. The pause is append-only: only `agent_run`/`agent_approval`
operational columns change, and the real tool result is appended when the
decision arrives.

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

#### Forking

`POST .../fork` accepts an optional `{at_entry_id?, title?}` body and returns
`201` with the new conversation. `at_entry_id` is an inclusive cutoff that must
belong to the source thread; it defaults to the latest entry. The default title
is `Fork of {source.title}`, clipped to 200 characters. The fork is always
active, gets a new `provider_session_id`, records `parent_conversation_id` and
`fork_at_entry_id`, and copies the immutable entries through the cutoff with new
ids and `commit_seq` values. Head markers and context edits are remapped to the
copied entries; references outside the cutoff are dropped. The source
conversation and its entries are never modified.

Forking copies transcript entries only. Runs, retry state, and approval state
are not copied, so the next user message starts a fresh run against the copied
context. An archived source returns `409 agent_conversation_archived`; an active
run returns `409 agent_conversation_busy`; a cutoff from another conversation
returns `400 agent_fork_entry_invalid`; a missing or soft-deleted source returns
`404 agent_conversation_not_found`. In the UI, the thread rail has a **Fork**
action for active threads (disabled with an explanation for archived threads),
and user/assistant entries expose **Fork from here**. Success shows a toast,
invalidates the thread list, and navigates to the new thread; the masthead shows
`Forked from #<id>` with a link to the source.

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

The current SPA does not attach a page snapshot, because the floating dock and
cross-page composer were removed. The API field remains available to external
clients; when a snapshot is present, the transcript renders it as a compact
context card rather than as a user question.

Tests inject a deterministic `FakeChatGenerator` from
`app/module/agent/test/fake_chat_generator.py` by setting
`app.state.agent_chat_generator` or overriding `get_agent_chat_generator`; no
DeepSeek call is made.

#### Known limitations

- Retry starts a fresh run with the same runtime snapshot policy but does not
  increase any budget. A transcript that already exhausted the token or tool
  result budget can reach the same limit again.
- Approval resolutions are single-writer. A process crash after an approval is
  claimed but before its tool result is appended fails the waiting run closed on
  the next startup rather than retrying the write automatically.
- Turning `save_memory_requires_approval` off only affects new calls. Pending
  approvals created while it was on stay pending until explicitly approved or
  rejected; they are never auto-approved by the setting change.

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
an authenticated account and only expose that account's saved questions. Create
and update reject unknown fields, so a client cannot supply an answer.
`question` is trimmed and limited to 32,000 characters.

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

The `/questions` page is a secondary workspace, linked from Search and the
method colophon. It uses the generated hooks and provides create, list,
pagination, edit, delete, and ask actions. Each card shows its status, answer,
citation chips, run error, last-asked time, and an **Open conversation** link
when a conversation exists. Ask is a synchronous JSON request, so the card shows
a pending state for the seconds the turn takes.

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

When a run pauses for `save_memory`, a persisted approval card appears in the
thread and in the dock. It shows the proposed memory, supersedes/occurred-at
context, the write risk, and **Approve write** / **Reject** actions. The card is
loaded from the durable approvals endpoint, so it survives a reload, and it is
disabled while a resolution streams or the thread is archived. Approve resumes
the run and appends the real tool result; Reject appends `memory_rejected` and
never writes.

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
citations resolve to File Library previews or memory readers. Saved questions
remain available at `/questions` for later agent turns.

The rail is grouped rather than flat. The archive workspaces come first (Chat,
File library, Timeline, Memory, Search, Dashboard), then a personal block with
**User profile**, then the system block (Settings, **Change password**,
**Accounts** for the root account only, About), and a separate **Session**
block with **Sign out**. The footer identity is also the root user switcher:
root clicks it to open a searchable account dialog, while normal accounts see a
plain identity block. While impersonating, the footer keeps the target account
and a small **Viewing as** marker, and a persistent banner above the page canvas
names the target and offers **Return to root**, which asks for the root password
before ending the session. Index numbers are computed from the rendered
position, so hiding Accounts and the switcher for a normal user leaves no gap. The root `/` opens Chat; the archive summary lives at
`/dashboard` with the `database` rail icon. Below 980 px the rail becomes a
navigation drawer opened from the mobile bar.

### Chat workspace

`/chat` is a fixed-height three-column workspace: a collapsible conversations
drawer, the stream column, and a tool inspector. A 12 px separator supports
pointer drag, click-to-collapse, and keyboard arrows/Home/End; the ratio and
collapsed state persist locally. Below 900 px the inspector becomes a tab. The
composer sends on Enter, inserts a newline on Shift+Enter, and exposes Stop while
streaming.

There is no second composer. The former floating dock and command palette were
removed; a saved question runs through `/chat` like any other turn.

Status bubbles describe observable work, not hidden chain-of-thought:
orienting, searching, reading, comparing, composing, saving, sealed, and error.
Each row can show the step, tool name, elapsed time, status, and a short result
summary.

The inspector keeps the resource the user is reading on screen. It follows the
newest tool call until the user pins a panel, offers **Follow current** to resume
following, and retains the last valid resource when a later tool has no resource.
Inspector panels reuse the same safe renderers and file/memory queries as the
File Library and Memory reader rather than adding a second rendering path.

| Tool | Inspector idea |
|---|---|
| `search_knowledge` | Result constellation across files, memories, and summaries; excerpts open in place |
| `read_file` | Manuscript chunk window with file id, chunk number, and citation |
| `read_timeline` | Time band with density, sampled events, and skip counts |
| `read_path` | Folder branch map that opens a folder or file directly |
| `read_memory` | Pressed-leaf memory chain with supersession neighbours |
| `save_memory` | Wax-seal receipt with status, memory id, and superseded ids |
| `present_resource` | Display stand that embeds the file or memory viewer |

Every panel provides loading, empty, error, and success states. Tool result
`data` carries the bounded, UI-only excerpts and viewer URLs that make these
panels possible; provider-facing tool content is unchanged.

The chat inspector, File Library workspace, and folder board are implemented in
the current release. The production client is compiled inside the Docker image
from `frontend/`, so a frontend change only needs an image rebuild.

### Resource preview

Files open in an in-situ preview modal inside the File Library; the Memory
reader is a normal route at `/memory/:id`. Legacy `/viewer/*` URLs redirect into
those surfaces, so old citations and bookmarks keep working.

| Resource | Renderer |
|---|---|
| PDF | `react-pdf` 11 + bundled `pdfjs-dist` 6, page navigation, zoom, fit width, text layer |
| DOCX | `docx-preview` inside a script-disabled sandbox |
| Image | native image with the standard file content endpoint |
| Text / JSON / Markdown / CSV | archive sheet with wrap/copy/download, pretty JSON, GFM Markdown |
| Memory | pressed-record memory leaf with lineage and trace link |

`GET /api/v1/files/{file_id}/content` serves originals inline with `nosniff`, a
sandboxing CSP, ETag/Last-Modified, and single-range HTTP Range support
(`206`/`416`; `If-None-Match` returns `304`). `/download` stays an attachment.
Legacy text-only records have `has_original=false`; the sheet skips the
`/content` probe entirely and reads indexed chunks.

PDF.js CMaps and standard fonts are copied from the pinned `pdfjs-dist` package
into `frontend/public/pdfjs/` by `bun run pdf-assets`, which `dev` and `build`
run automatically. Vite emits them into `frontend/dist/pdfjs/` during the image
build, so they ship with the rest of the bundle. They are served locally and
never fetched from a CDN.

### Accounts, roles, and sessions

On the first visit the app asks you to create the root account. There is no
default password and no email recovery. The root can then create normal
accounts from **Accounts**; a new account is created with a generated
20-character temporary password that is shown once, and it must choose a new
password before any archive content loads. Root can disable, enable, reset, and
impersonate other accounts. Disabling an account or resetting its password
revokes its sessions; revocation is checked at request start, so an SSE turn
that was already streaming may finish its current run. Accounts are never
deleted, so a username stays reserved.

**Accounts** now uses larger information cards. Each card carries the avatar,
name and `@username`, role/state badges, creation date, last sign-in, and the
rolled-up agent usage for that account: total, prompt, completion, and cached
tokens, API calls, turns, and the last activity. The prompt/completion split is
drawn as a small bar, and accounts with no agent activity still show a readable
zero state. Usage is counted per agent run and rolled up by a database trigger,
so the card stays a cheap root-only list read rather than a cross-account
conversation scan.

Root can start an impersonation session from the footer user switcher or from a
normal active account card. The dialog searches the root-only account list
locally, excludes root accounts, and refuses disabled accounts or accounts that
must change their password. Impersonation is a deliberate trusted root
capability: the cookie becomes the target account's session with an
`impersonator_user_id` marker, the target's role controls every normal
authorization decision, and root-only pages disappear. The persistent banner
names the target and offers **Return to root**, which requires the root password,
deletes the impersonation session, and issues a fresh root session. Requiring
the password prevents the impersonated person from taking over root. Password
changes are rejected while impersonating. A session transition in one tab
reloads the other tabs so stale DOM, drafts, dialogs, and account-scoped query
rows cannot survive; the last-chat resume pointer is also cleared. This is not
an RLS bypass; it is another way for the highest-trust account to act as someone
else, just like resetting their password.

Both roles use the same private archive surface. The root additionally manages
accounts and global settings, but is not a data superuser: the API and
PostgreSQL row-level security prevent it from reading another account's files,
memories, or conversations through normal queries. Password reset and explicit
impersonation are the trusted-recovery exceptions: root can issue a temporary
password or open the target's session, and therefore could sign in as that
account. Protect the root credential accordingly; RLS is not a defense against
a malicious root who uses those capabilities. Normal users do not see the
global Settings tabs or the **Accounts** page; their Settings shows only
**Frequent prompts** and **Language**, while root sees all eight tabs. Dashboard
and stats counts are scoped to the signed-in account; AI status is global and
read-only. Passwords are hashed with Argon2; the database stores only a SHA-256
hash of each session token. The cookie is HttpOnly, SameSite=Lax, and Secure
when `APSOR_COOKIE_SECURE=true` (the Cloudflare compose sets it). Each
account can edit its display name and any number of ordered title/content
profile cards at `/profile`; the name labels chat turns and the cards are frozen
into new conversations as the `user_profile` system section. The sign-in
username stays immutable.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/auth/status` | First-run state and current session |
| `POST` | `/api/v1/auth/setup` | Create the root account (first run only) |
| `POST` | `/api/v1/auth/login` | Verify a password and set the session cookie |
| `POST` | `/api/v1/auth/logout` | Delete the session and clear the cookie |
| `POST` | `/api/v1/auth/password` | Change the signed-in password; allowed while a change is forced |
| `GET` | `/api/v1/auth/me` | Current account (requires a session) |
| `GET` | `/api/v1/auth/profile` | Display name plus every ordered profile card |
| `PUT` | `/api/v1/auth/profile` | Replace the display name and all cards atomically |
| `GET` | `/api/v1/accounts` | List every account, root first (root only) |
| `POST` | `/api/v1/accounts` | Create a normal account and return a one-time temporary password (root only) |
| `POST` | `/api/v1/accounts/{user_id}/disable` | Disable an account and revoke its sessions (root only) |
| `POST` | `/api/v1/accounts/{user_id}/enable` | Re-enable an account (root only) |
| `POST` | `/api/v1/accounts/{user_id}/reset-password` | Replace another account's password (root only) |
| `POST` | `/api/v1/accounts/{user_id}/impersonate` | Replace the root cookie with a normal target-account session (root only) |
| `POST` | `/api/v1/auth/impersonation/stop` | Verify the root password, delete the impersonation session, and issue a fresh root session |

Every knowledge, settings, prompt, and agent endpoint requires a signed-in,
active account. Root-only settings and account routes return `403 forbidden` to
a normal user, and a session with `must_change_password=true` can reach only the
auth status, password-change, and logout endpoints until it changes the
password. Only `/api/v1/health`, `/health`, `/api/v1/auth/status`,
`/api/v1/auth/setup`, `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/docs`,
`/api/redoc`, `/openapi.json`, and the SPA shell are public. Tool endpoints need
the session cookie too.

Document intake (`POST /api/v1/files`) supports:

- **Images** (`jpg`, `jpeg`, `png`, `webp`) — DeepSeek vision caption + OCR when
  configured; otherwise a filename-derived caption with
  `extraction_method=filename`. Images remain normal File Library files.
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

Interactive docs: <http://127.0.0.1:8000/api/docs>. The OpenAPI schema is the source
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

## How retrieval works

1. **Normalize** with NFKC and lower-case. Punctuation becomes whitespace.
2. **Index** overlapping CJK bigrams, Latin words, and Latin trigrams. Each chunk
   stores a unique n-gram list with term frequencies.
3. **BM25** scores candidates (`k1=1.2`, `b=0.75`). A union query such as
   `automobile ford` naturally favours chunks that contain both terms.
4. **Vector recall** uses a 384-dimensional signed feature-hashing embedder by
   default, so it works offline. Set `APSOR_EMBEDDING_PROVIDER=openai` and the
   matching base URL/model to use a hosted embedding model instead.
5. **Fuse** with reciprocal rank fusion. Each source kind keeps its own top
   `result_number`, so a summary cannot be crowded out by file chunks.
6. **Deduplicate** by chunk id, then hydrate the file, memory, or summary row.

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
APSOR_EMBEDDING_PROVIDER=openai
APSOR_EMBEDDING_BASE_URL=https://api.openai.com/v1
APSOR_EMBEDDING_MODEL=text-embedding-3-small
APSOR_EMBEDDING_DIMENSION=1536
APSOR_EMBEDDING_API_KEY=sk-...
EOF
chmod 755 .secrets
sudo chgrp 10001 .secrets/openai.env
chmod 640 .secrets/openai.env
```

The Settings page can also store this configuration in the database. After
changing the embedding model, open Settings and run **Re-embed library** (or call
`POST /api/v1/settings/providers/embedding/reindex`) so existing chunks get vectors in
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
  handles exact terms, but query phrasing matters.
- **Deterministic.** The same text always produces the same vector, which makes
  ingestion and tests reproducible.
- **Exact scan at personal scale.** The current implementation scans up to
  20,000 current vectors and computes cosine in Python. At a larger corpus,
  replace it with pgvector/HNSW or a hosted embedding model; the
  `EmbedderProtocol` boundary stays the same.


## Data model

The schema follows three rules: source metadata lives in its owning table, the
unified chunk table stores only the source key, and every private row carries
exactly one owner.

```text
file ─────────────┐
folder ───────────┤
memory ───────────┼──> chunk ──> chunk_ngram
memory_summary ───┘
```

The private archive tables below carry `user_id bigint NOT NULL`. The exceptions
are the global config tables (`agent_config`, `ingest_config`,
`system_prompt_section`, and the four provider tables), which are shared
deployment configuration, and the auth tables (`app_user`, `user_session`),
which hold identity rather than archive content.
Parent/child links in private tables use composite `(id, user_id)` foreign keys,
so a row cannot point into another account's lineage. Forced PostgreSQL
row-level security on the `apsor_app` role is the database backstop; request
transactions set `app.user_id` for the duration of one transaction. Auth tables
deliberately stay outside RLS because login and session lookup happen before a
user context exists; global config tables are read-all/root-write.

- `file`: one row per version. `is_current` and `deleted_at` are soft state;
  ids are never reused. File leaves are not duplicated in the folder table:
  their placement is `raw_file_path`. `storage_backend` records `local` or `r2`
  for the original bytes and is null exactly when `storage_key` is null.
- `folder`: explicit folder records (`parent_id`, `path`, `name`, `depth`).
  Empty folders and folder identity survive independently of files. Uniqueness
  is per account: `(user_id, path)`.
- `chunk`: `(source_kind, source_id, chunk_index)` with an optional JSONB vector.
- `chunk_ngram`: the inverted index used by BM25.
- `memory`: linear timeline with an auto-generated `title`, `supersedes_ids`,
  `superseded_by_id`, `status=active|deprecated`, and the direct-retirement
  provenance `deprecated_at` / `deprecated_reason`. A deprecated row must have a
  successor or a `deprecated_at` timestamp.
- `memory_summary`: period, source memory ids, themes, generator, and model.
- `chat_provider_config` / `embedding_provider_config` /
  `web_search_provider_config` / `web_fetch_provider_config`: one row per saved
  provider, with an encrypted API key, a safe hint, and the model/base
  URL/dimension. A partial unique index on `is_active` enforces one active row
  per capability. `web_search` and `web_fetch` are independent credentials.
- `app_user`: one row per account. `role` is `root` or `user`; `is_active`,
  `must_change_password`, `disabled_at`, `created_by_user_id`, and the password
  audit timestamps model the account lifecycle. A partial unique index enforces
  exactly one root, and usernames stay globally unique and immutable.
- `user_profile_card`: ordered title/content cards that describe the account; the
  full set is frozen into a new conversation as the `user_profile` section.
- `frequently_used_prompt`: private, account-editable shortcuts for the empty
  chat page, ordered by `sort_order` and capped at 20 rows per account.
- `agent_conversation` / `agent_entry` / `agent_run`: the persistent agent's
  transcript scope, immutable entry log, and per-submission run state.
  `agent_commit_seq` groups entries written in one transaction. Page snapshots
  are `pi.page-context` entries in the same log, not a separate table.
- `agent_approval`: durable pending/approved/rejected/expired human decisions for
  confirmation-required writes, with validated arguments, a safe preview, and
  the loop snapshot used to resume the waiting run.
- `agent_config`: one row (`id=1`) with the validated runtime limits used by the
  agent loop and the settings API.
- `saved_question`: the account's Q&A library. `question` is user-authored;
  `answer`, `citations`, `conversation_id`, and the run status/error fields are
  written only by an ask. `conversation_id` uses `ON DELETE SET NULL`, and
  `last_asked_at` records the most recent attempt.
- `file_ingest_job`: the durable intake queue. It stores the source kind, path,
  payload key and backend, status/stage, `progress_pct`, chunk counts, bounded
  error fields, and attempt/timestamps. A path can have only one active job per
  account. The job points at its staged file, clears that link on failure, and
  the file and chunks become current only when the job publishes them.
- `ingest_config`: one row (`id=1`) with the validated worker poll, extraction,
  in-flight, embedding, and chunk-size settings. It is not a chunk source; the
  queue references the file that is eventually published.

Original bytes are not stored in PostgreSQL. They live on local disk or in the
private R2 bucket, selected per file by `storage_backend`; the extracted chunks
and their n-grams remain in PostgreSQL.

The committed code, comments, UI copy, and documentation are English.

## Development checks

```bash
# Backend
cd backend
uv run ruff check .
uv run mypy app
PYTHONUTF8=1 uv run bandit -r app -c pyproject.toml
uv run pip-audit
PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/apsor-archive-pytest.log

# Frontend
cd frontend
bun run lint
bun run typecheck
bun run build
bun audit
```

The integration suite uses one real PostgreSQL test database
(`apsor_archive_test`) on the same instance, runs sequentially, and resets every
tracked table between tests. The database is built by `alembic upgrade head`,
not `create_all`, so the `apsor_app` role, grants, and RLS policies are present
in every request. There are 46 collected tests; each one exercises the real HTTP
surface and database. The multi-user tests cover the root/user lifecycle,
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

The latest migration is `a4c8e2f6b9d1`, after `f9c2a7d4e6b1`. The migrations
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
- `a4c8e2f6b9d1` (current head) removes the `max_total_tokens` column and its
  check constraints, repairs a compaction threshold that is not below its
  context window, and replaces the old threshold rule with
  `compaction_threshold_tokens < context_window_tokens`. The downgrade restores
  a 100,000-token ceiling and raises it when the stored threshold requires it.

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
    module/web_research/        Tavily search/fetch service, URL safety, cache
  alembic/                      migrations
  tests/                        46 integration tests
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
    library/                    files, media gallery, preview modal, intake
    home/ search/ timeline/ memory/ about/ ...
  src/apis/fetch-client.ts      the only JSON mutator
  src/apis/agent-stream.ts      SSE transport for agent turns
  src/lib/                      formatting and safe highlighting
  src/styles/                   paper / night archive tokens
  scripts/copy-pdfjs-assets.mjs copies pinned PDF.js CMaps/fonts
  dist/                         generated build output, gitignored
docker-compose.yml              normal deployment
docker-compose.dev.yml          local dependencies
docker-compose.cloudflare-tunnel.yml   Cloudflare Tunnel deployment
docs/cloudflare-tunnel.md       Tunnel deployment, backup, and security guide
docker/caddy/                   non-root reverse proxy for the tunnel
```

## Security and privacy

- Complete first-run setup before exposing the service. While no account exists,
  `/api/v1/auth/setup` is public by design; do not leave a fresh instance
  reachable through a tunnel before the root account is created.
- One root plus normal accounts protect the archive. Passwords are hashed with
  Argon2; session tokens are stored only as SHA-256 hashes in `user_session`.
  The cookie is HttpOnly, SameSite=Lax, and Secure when
  `APSOR_COOKIE_SECURE=true`. A temporary password is returned once, never
  logged or cached, and the account must change it before loading content.
- Every private row carries `user_id`; composite foreign keys keep lineage
  inside one account, and PostgreSQL forced row-level security on `apsor_app`
  denies cross-account reads and writes even if a service filter is missing.
  Root-only route guards protect accounts and global settings, but root is not a
  data superuser and cannot read another account's archive through normal API
  queries. Root password reset and explicit impersonation are deliberate
  trusted-recovery capabilities that can transfer sign-in access to the target
  account; stopping impersonation requires the root password, deletes that
  session, and issues a fresh root session. Treat root as the highest-trust
  credential and do not model RLS as protection against a malicious root.
- **RLS is an application boundary, not a host boundary.** The deployment login
  is a PostgreSQL superuser used for migrations and maintenance; the app
  switches to `apsor_app` for request transactions. Any local OS user, any
  container on the database/cache network, or anyone who can read
  `.secrets/`/`.env` can bypass the API and RLS. Keep the host trusted, keep the
  database and cache bound to localhost or an internal network, use distinct
  host accounts, set a strong database/cache password for any shared host, and
  rotate credentials after exposure. A future hardening step is a dedicated
  non-superuser runtime login plus a separate maintenance credential.
- The normal Compose file binds the API to `127.0.0.1`; the Cloudflare file
  publishes no host port. Login throttling is in-memory and therefore
  single-process; run one API process, or move the throttle to Valkey before
  scaling out.
- Paths reject traversal segments, backslashes, control characters, and
  over-long values. Uploads are capped at 10 MB and restricted to an extension
  allowlist.
- HTML from files and memories is rendered as text through React. Agent Markdown
  uses `skipHtml`; DOCX previews run in a script-disabled sandbox. The UI never
  uses `dangerouslySetInnerHTML`.
- The DeepSeek key lives in `.secrets/deepseek.env` or the environment. It is
  never logged, returned, or committed. Keys saved from the Settings page are
  encrypted in PostgreSQL and returned only as a four-character hint.
- R2 credentials live in the gitignored `.secrets/r2.env`, are mounted
  read-only, and never become container environment variables. The bucket is
  private, with no presigned or public URLs.
- AI calls happen for summaries and agent turns. If the provider fails, the API
  returns a stable error instead of inventing an answer.

## License

MIT. See `LICENSE`.
