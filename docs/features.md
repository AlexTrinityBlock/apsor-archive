# Features in depth

**English** · [繁體中文](zh-TW/features.md) · [简体中文](zh-CN/features.md)

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
> dedicated PDF/DOCX/PPTX/spreadsheet/image/text preview engines, a folder workspace,
> and a three-panel chat workspace.


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
- **Agent limits are database-backed.** The step and tool caps, parallel width,
  result budgets, and compaction controls live in one validated `agent_config`
  row and apply to new runs without a restart. Each account's primary model and
  context budget are separate assignments: the context window is a real
  per-account input budget, not model metadata, and the agent enforces it
  locally instead of failing the turn.
- **Chat models are assigned per account.** Root links each account to a saved
  chat endpoint plus a free-text model and reasoning effort for agent chat, and
  a second endpoint for summaries, memory, ingestion, and vision. A changed
  connection must pass a real provider probe before it can be saved. Provider
  rows hold the encrypted key, so rotating a key affects every account assigned
  to that endpoint.
- **Long threads can be folded or cleared.** Compaction writes a summary
  boundary; clear starts an empty active context. The full transcript remains
  readable in both cases.
- **Memories are linear and traceable.** A new belief can supersede an old one.
  The old memory leaves the search surface but stays readable through its chain.
- **Search is hybrid.** BM25 over CJK bigrams and Latin tokens runs beside vector
  recall. Results are de-duplicated and fused, with the reason recorded. Past
  conversation messages are also indexed as raw 256-character windows; a
  separate cosine → BM25 → RRF lane returns the best 15 windows, and the agent
  can expand any hit by its stable message id.
- **Time is sampled honestly.** The agent's timeline tool returns up to five
  anchors per event kind and reports exactly how many events were skipped. The
  human Timeline page requests the complete selected window (`complete=true`)
  and loads earlier windows automatically as you scroll.
- **AI answers are grounded.** The assigned chat model receives retrieved
  passages, not the whole library, and every claim must carry a citation.
  Without a usable assignment, agent turns fail closed with a stable code.
- **Questions outlive the conversation.** Save a question before you have an
  answer, ask it later, and keep the answer, its citations, the run status, and
  a link to the conversation on the same row. Editing the question clears the
  stale answer instead of leaving a mismatched pair on screen.
- **Chat images are temporary.** A screenshot pasted into the chat composer is
  uploaded immediately, with per-image byte progress, to the signed-in account's
  `users/{user_id}/chat-temp/` object-storage area, downscaled, re-encoded, and
  listed in a removable temporary-image manager. Sending stays disabled until
  every selected image is stored. Removing an unsent image or leaving the chat
  aborts its upload and discards the staged row immediately; staged images left
  behind by a closed tab expire after the database-configured lifetime (one hour
  by default). Sending a message promotes
  the object to `users/{user_id}/chat-images/` before claiming the row, so sent
  images are durable until the owner deletes them. The provider receives an
  OpenAI-compatible `image_url` part. Deleting a chat image removes the object
  and leaves an honest placeholder in the transcript. Chat images are not
  archive files and are not searchable.
- **Images live in the File Library.** An image is a normal file record with its
  original bytes, path, and chunks. A vision-capable chat provider adds OCR,
  GitHub-Flavored Markdown tables, and a complete visual description; the OCR
  text stays in its original language while the description language and the
  image/document prompt templates are root-only settings. Each vision-extracted
  file records the SHA-256 of the exact rendered prompt, its mode, and the
  description language. Without a provider, a filename-derived caption keeps
  local uploads searchable. There is no separate image index.
- **Vision prompts are editable, without prompt version history.** Root can
  replace the full image and scanned-page system prompts. Saving validates only
  that the nine output JSON keys remain present; the current templates live in
  `ingest_config`. Existing files keep their extraction until an explicit
  re-ingest creates a new file version.
- **Documents choose their extractor.** PDFs try text first and fall back to
  vision for scanned pages. DOCX, PPTX, TXT, JSON, CSV, and logs use text, with
  AI structured metadata; images use vision or the filename fallback. XLSX, XLS,
  XLSM, and ODS workbooks are read sheet by sheet into Markdown tables, including
  dates, numbers, merged headers, hidden sheets, and formula fallbacks; they
  never enter the vision path.
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
- **Original bytes live in S3-compatible storage.** The bundled RustFS service
  is the default; Cloudflare R2, any S3 endpoint, or local disk can be chosen
  in the setup wizard. Reads follow the backend recorded on each row, so a
  staged migration can serve a mixed archive. Buckets stay private and the app
  never issues presigned or public URLs.

## Tool surface

The archive exposes six small HTTP tools. Each JSON endpoint mirrors a retrieval
or memory operation the agent can call; each payload is deliberately small enough
for an LLM to use in sequence.

| Tool | Endpoint | What it returns |
|---|---|---|
| `search_knowledge` | `GET /api/v1/search?query=&result_number=2` | Top results per archive source kind from BM25 + vector, fused with RRF; plus the top 15 past-conversation windows |
| `read_file` | `GET /api/v1/files/{file_id}/chunks/{chunk}?chunk_range=1` | A 1-based chunk window |
| `read_timeline` | `GET /api/v1/timeline?year=&month=&day=&day_range=1` | Sparse by default: up to five sampled events per kind, density, and skip counts; `complete=true` returns the whole window |
| `read_path` | `GET /api/v1/paths?path=/history&path_depth=1&fuzzy_search=` | Directories and files, or fuzzy path matches |
| `save_memory` | `POST /api/v1/memories` | A new memory with an auto-generated title, the deprecated memories it replaced, and any new summary; omit `content` to deprecate `supersedes` ids without a replacement |
| `read_memory` | `GET /api/v1/memories/{memory_id}?memory_range=1&trace_history=true` | Target, neighbours, supersedes, successor, and chain |

The agent tool and `/api/v1/tools/read_timeline` keep the sparse default; the
Timeline page adds `complete=true` for the selected window and auto-loads the
previous window when you scroll. Complete responses report `mode="complete"`,
`sampled == total == len(events)`, `skipped=0`, empty `skips`, and an
`anchor=null` on every event. The page excludes its event spine from the page
context, so the complete list is never sent to the agent as context.

The persistent archive agent exposes ten model tools: the six above plus
`present_resource`, `web_search`, `web_fetch`, and `history_message`. The HTTP
examples use explicit parameters; the HTTP server defaults are
`result_number=2`, `chunk_range=1`, `day_range=1`, `path_depth=1`, and
`memory_range=0`. File text is chunked at about 4,000 characters with a
500-character overlap; existing files keep their original chunk boundaries until
re-ingested. Past conversation messages use a separate fixed window: 256
characters with a 32-character overlap (stride 224). The agent's tool schemas
choose their own defaults, such as `result_number=8` and `day_range=7`.
`history_message` takes the `id` shown on a `<history_message>` search hit and
returns the full message plus bounded neighbours. For external LLM callers, the
separate `/api/v1/tools/*` facade renders the same services as compact XML; the
persistent agent calls the services directly through its own registry.

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
`reason`), `GET /api/v1/memories/{memory_id}/related` and
`GET /api/v1/memories/related/files/{file_id}` (related memories from stored
embeddings and keywords; no provider call), `POST /api/v1/summaries`, `GET /api/v1/stats`,
`GET /api/v1/health`, and `GET /api/v1/ai/status`. `ai/status` reports the
deployment-global runtime for root diagnostics; it is not an account's model
assignment.

### Folder workspace

`/library` is a folder-first workspace. A breadcrumb and folder rail describe
where you are; the main area shows folder cards and file cards for the current
path. The previous table remains available as a compact list view for dense
browsing, selected explicitly with `view=list`.

- **New folder** creates the requested folder and any missing ancestors. The
  operation is idempotent: repeating it returns the same folder with `201`.
- **Drag upload** accepts files dropped from the desktop onto a folder card or
  the current folder surface. The upload uses the same intake path, extension
  allowlist, and server limits as the upload dialog: 10 MB per uploaded file
  and `.md`, `.markdown`, `.txt`, `.csv`, `.json`, `.jsonl`, `.toml`, `.ini`,
  `.env`, `.log`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.xls`, `.xlsm`, `.ods`,
  `.jpg`, `.jpeg`, `.png`, or `.webp`. The dialog also supports a 2 MB
  plain-text creation. Dropped files are never opened or executed.
- **Clipboard paste** uploads files through the same intake path. When the
  clipboard name already exists in the target folder, the paste gets the first
  free ` (n)` suffix (`image (1).png`) instead of silently becoming a new
  version; pasting several files with one name numbers each in order. Dragging
  or using the upload dialog keeps the explicit same-name version behavior.
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
  entries. `model` is the canonical provider message text; linked temporary
  images are materialized as `image_url` parts at provider-call time, and `data`
  is UI/diagnostics only.
- `agent_run` — durable state for one submission (`request_id`, status, abort,
  last entry, safe error). `agent_commit_seq` groups entries written in one
  transaction.
- `agent_approval` — one durable pending/approved/rejected/expired human decision
  for a confirmation-required tool call, including validated arguments, a safe
  preview, and the loop snapshot used to resume the waiting run.
- `agent_chat_attachment` — chat images owned by one account, with the
  object-storage key, sanitized metadata, and an optional link to the user entry
  that sent them. Unsent images live under `users/{user_id}/chat-temp/`; sending
  promotes them to `users/{user_id}/chat-images/`. Rows are soft-deleted.
- `agent_config` — the singleton runtime configuration (`id=1`) holding the
  validated token, step, tool, page-context, compaction, and chat-image lifetime
  limits.

User and assistant entries are also copied into the shared flat chunk index as
`source_kind='history'`, with one row per 256-character window. The background
history indexer backfills existing conversations, skips empty tool-call-only
assistant entries, and marks a soft-deleted conversation's windows non-current.
The agent sees each hit as `<history_message id="...">` and calls
`history_message` to read the full immutable entry and its neighbours.

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
| `POST` | `/api/v1/agent/attachments` | Upload one temporary chat image (`multipart/form-data`, optional `client_token`) |
| `POST` | `/api/v1/agent/attachments/cancel` | Idempotently discard a staged upload by `client_token` (`204`) |
| `GET` | `/api/v1/agent/attachments?status=&limit=&offset=` | List the account's temporary chat images |
| `GET` | `/api/v1/agent/attachments/{attachment_id}/content` | Stream one live temporary image |
| `DELETE` | `/api/v1/agent/attachments/{attachment_id}` | Delete the object and soft-delete its row (`204`) |
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
`{content, attachment_ids?, request_id?, page_context?, client_timezone?,
client_utc_offset_minutes?}` and `.../retry` accepts `{request_id?}`. Up to four
staged chat images may be attached; text may be empty when an image is present.
Both stream
`text/event-stream` by default. The client timezone is stored with a
server-rendered `<current_time>` block on each user entry; the block is appended
after the message text exactly once. The ordered system prompt sections are
written at conversation creation and frozen into that thread. The four defaults
are seeded as ordinary rows; Settings lets the root account edit, delete, or
reorder every row for the whole deployment. The event names are
`run_start`, `message_start`, `message_delta`, `reasoning_delta`, `message_end`,
`tool_start`, `tool_end`, `approval_required`, `run_end`, and `error`.
`reasoning_delta` carries provider reasoning text that arrived before the
corresponding answer or tool call and is never merged into `message_delta`. `run_start` reports
`page_context_entry_id` (or `null`), `page_context_attached`, and `resumed` so
the client can mark whether a new snapshot was written and whether the stream
continues a durable waiting run. `tool_start` and `tool_end` also carry
`parallel`, `batch_size`, and `parallel_index` for the assistant call batch.
`tool_end` carries the persisted tool-result `data` payload plus `duration_ms`
and `error_code`, so the inspector can render previews before the transcript
refetch settles. `message_start` has `entry_id=null` because the assistant entry
is persisted only at `message_end`; deltas are transport-only. Provider
reasoning is kept as bounded display telemetry in the assistant entry and shown
as a plain-text `Thinking` block; it never enters provider messages, the frozen
system prefix, or the cache-prefix hash. A deterministic compaction summary may
carry one bounded `Thinking:` line. Send
`Accept: application/json` for the completed turn instead. SSE responses set
`Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`, and
Starlette's GZip middleware excludes `text/event-stream`.

Each conversation allows one active run at a time. The defaults allow 6
parallel tools, 75,000 tokens of active context before auto compaction, and
100,000 result characters per tool. There is no step cap, tool-call cap, or
cumulative per-turn token ceiling; a turn ends only on a final answer, a user
cancellation, or a provider failure. The effective context window is the
deployment default (1,000,000) unless the
account assigns its own budget; it is the real outbound input budget enforced by
the local overflow ladder, and the compaction threshold must stay below it. The
budget estimate weights CJK characters at roughly 1.6 characters per token while
ASCII text keeps the model catalog ratio, and the largest successful
provider-reported `prompt_tokens` in the current context segment is used as a
floor. `context_used` in the provider-only status block is therefore
conservative, not a provider-exact token count. Each
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
retry can still be rejected by the provider if even the overflow ladder cannot
fit the request. The endpoint returns `409 agent_run_not_retryable` when the latest run
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
`compaction_threshold_tokens`, the turn appends a `pi.compaction` entry before
the next provider call. The check runs before a new user turn and again after
tool or page-context growth inside a running turn, so a full context compacts
instead of failing the provider call:

- The entry sets `head_entry_id` to its own id, so older entries stay immutable
  but fall outside the new active context.
- Its provider message starts with `<compaction>` and carries
  `<last_user_input>` (the last user input before compaction) and `<summary>`.
- The same transaction writes compaction → page context (when the page is
  reattached) → user, so the model sees the summary before the new request.

Compaction is deterministic: it never calls a provider. The summary is bounded
by `compaction_max_output_tokens` (2,600 by default) and rendered from the
root-editable `compaction_prompt`, which must contain `{max_output_tokens}`; the
legacy character caps still apply. The overflow ladder can also build an
ephemeral compaction for one outbound request without appending a boundary.

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
entries as user marginalia, archive sheets, field-note tool results, and
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
File library, Timeline, Search, Dashboard; memories are the File library's
Memories tab), then a personal block with
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

Files open in an in-situ preview modal inside the File Library; memories live
in its Memories tab, with the reader at `/library/memories/:id` and a Related
memories section ranked from stored embeddings, shared keywords, and shared
summaries. Legacy `/memory/*` and `/viewer/*` URLs redirect into those surfaces,
so old citations and bookmarks keep working.

| Resource | Renderer |
|---|---|
| PDF | `react-pdf` 11 + bundled `pdfjs-dist` 6, page navigation, zoom, fit width, text layer |
| DOCX | `docx-preview` inside a script-disabled sandbox |
| PPTX | `pptxviewjs` Canvas renderer with slide navigation and keyboard arrows |
| Spreadsheet (XLSX/XLS/XLSM/ODS) | lazy SheetJS grid with sheet tabs, hidden-sheet markers, sticky headers and a bounded 500 × 50 preview |
| Image | native image with the standard file content endpoint |
| Text / JSON / Markdown / CSV | archive sheet with wrap/copy/download, pretty JSON, GFM Markdown |
| Memory | pressed-record memory leaf with lineage and trace link |

`GET /api/v1/files/{file_id}/content` serves originals inline with `nosniff`, a
sandboxing CSP, ETag/Last-Modified, and single-range HTTP Range support
(`206`/`416`; `If-None-Match` returns `304`). `/download` stays an attachment.
Legacy text-only records have `has_original=false`; the sheet skips the
`/content` probe entirely and reads indexed chunks.

Every uploaded image, PDF, and Office file with an embedded preview also gets a
tiny WebP thumbnail during ingestion (`GET /api/v1/files/{file_id}/thumbnail`).
Library cards, the Media grid, chat resource cards, and preview loading states
paint it first inside a box sized from its known dimensions, so nothing jumps
or flickers while the full preview loads. The ingestion worker backfills
thumbnails for files uploaded earlier (`APSOR_THUMBNAIL_BACKFILL_ENABLED`, on
by default).

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
password before any archive content loads. A new account also inherits the
deployment's primary chat endpoint and model, so chat and background AI work
immediately; if the deployment has no active chat endpoint, the account starts
unassigned and root must assign one before AI features respond. Root can
disable, enable, reset, and
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

Each card also summarizes the account's model assignment. Root opens **Model**
next to the token quotas to assign the primary and auxiliary endpoints, their
free-text model and effort, and the optional context budget, or to reset both
slots. The account itself sees the same two slots read-only under **Settings →
Model**; only root can change them.

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
**Frequent prompts**, **Model**, and **Language**, while root sees all nine
tabs. Dashboard and stats counts are scoped to the signed-in account; AI status
is the deployment-global runtime diagnostic, not the account's model
assignment. Passwords are hashed with Argon2; the database stores only a SHA-256
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

- **Images** (`jpg`, `jpeg`, `png`, `webp`) — DeepSeek vision extraction when
  configured: OCR text in the original language, GitHub-Flavored Markdown
  tables, and a complete visual description in the configured description
  language. Without a provider, a filename-derived caption is used with
  `extraction_method=filename`. Images remain normal File Library files.
- **PDF** — pypdf text first; when the text is empty, garbled, or the AI
  structured analysis says `use_vision`, render up to 10 pages with pypdfium2
  and run document-page vision: OCR, tables, and a brief layout note.
- **DOCX** — python-docx paragraphs and tables; embedded images can provide a
  vision fallback with full image-mode descriptions and tables.
- **PPTX** — python-pptx slide text frames, tables, grouped shapes, and speaker
  notes; embedded `ppt/media` images can provide a vision fallback with full
  image-mode descriptions and tables. Legacy binary `.ppt` is not supported.
- **XLSX / XLS / XLSM / ODS** — python-calamine reads worksheets in order,
  including hidden sheets and merged cells, and renders each sheet as a
  GitHub-Flavored Markdown table. Cached formula values are preferred; for OOXML
  workbooks, openpyxl recovers formula text when a generated file has no cached
  result. Extraction keeps at most 10,000 rows per sheet and 100 columns, with
  an explicit truncation marker; the workbook text budget is 4,000,000
  characters and is lowered automatically to keep the output below the existing
  500-chunk-per-file ceiling. Raw values are indexed; cell display formats such
  as currency symbols, percent signs, and leading zeros are not reproduced.
  Spreadsheet extraction is text-only and never uses vision.
- **TXT / MD / CSV / JSON / LOG** — direct text plus AI structured metadata
  (title, summary, tags, document_type).

Every vision-extracted file records `vision_prompt_sha256`,
`vision_prompt_mode` (`image` or `document`), and
`vision_description_language`; legacy rows keep `null`, meaning the prompt was
not recorded. A custom prompt applies only to future ingests. Use the re-ingest
route above to create a new version from the stored original; text files are not
eligible, and a DOCX or PPTX with no embedded images keeps a text-only result
without a prompt fingerprint.

The same intake is available asynchronously through
`POST /api/v1/files/async` and `POST /api/v1/files/text/async`; poll
`GET /api/v1/files/ingest-jobs/{id}` for stage and chunk progress. See
**Ingestion runtime** above.

Interactive docs: <http://127.0.0.1:8000/api/docs>. The OpenAPI schema is the source
for the committed Orval client.
