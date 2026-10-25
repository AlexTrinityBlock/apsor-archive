# Apsor Archive Frontend

React 19 + TypeScript + Vite single-page archive. The production build is
committed under `dist/` and served by FastAPI.

## Scripts

```bash
bun install
bun run pdf-assets        # copy PDF.js CMaps/fonts into public/pdfjs
bun run dev               # pdf-assets, then Vite on 127.0.0.1:5173
bun run build             # pdf-assets, tsc -b, vite build
bun run typecheck
bun run lint
bun run api:generate      # Orval from the committed ./openapi.json
bun run api:generate:live # Orval from a running API on :8000
```

`dev` and `build` run `pdf-assets` automatically. The copied files live in
`public/pdfjs/` (gitignored) and are emitted to `dist/pdfjs/`; the Docker image
copies the committed `dist/`, so commit `dist/pdfjs/` with every production
build.

## Structure

```text
src/
  apis/fetch-client.ts          JSON fetch mutator; throws ApiError
  apis/agent-stream.ts          SSE parser for agent turns
  app/
    component/                  shared shell, panels, badges, toast
    generated-apis-types/       committed Orval client (incl. agent)
    hook/                       scroll lock, debounce, media queries
    type/                       UI types and local demo shapes
    agent/                      page context, trace, inspector panels
    home/ search/ timeline/     workspace routes
    library/                    files, media gallery, preview modal, intake
    memory/                     vault, pressing room, reader
    chat/                       persistent agent workspace
    questions/                  saved-question Q&A library
    method/ settings/
  lib/                          formatting, safe text highlighting
  styles/                       mono archive design tokens
scripts/copy-pdfjs-assets.mjs   pinned PDF.js runtime assets
```

Each page owns its components under `<page>/component/` and its page-specific
CSS under `<page>/<page>.css`. Shared visual primitives live in
`app/component/`; the design tokens live in `styles/tokens.css`.

## API generation

Orval reads the committed `frontend/openapi.json` by default, so generation
works without a running backend (the Docker build only copies the committed
`dist/`):

```bash
# from the repository root after a backend contract change
cd backend && uv run python -m script.export_openapi
cd ../frontend && bun run api:generate

# or generate directly from a running API
bun run api:generate:live
```

The generated hooks cover normal JSON routes, including `createFolder`,
`moveFile`, `copyFile`, `getAgentSettings`, `updateAgentSettings`,
`resetAgentSettings`, `compactAgentConversation`,
`clearAgentConversation`, `listSavedQuestions`, `createSavedQuestion`,
`updateSavedQuestion`, `deleteSavedQuestion`, `askSavedQuestion`,
`uploadFileAsync`, `createTextFileAsync`, `getIngestJob`, `listIngestJobs`,
`retryIngestJob`, `getIngestSettings`, `updateIngestSettings`, and
`resetIngestSettings`. Two deliberate exceptions use same-origin `fetch`
directly: `src/apis/agent-stream.ts` for `text/event-stream`, and the viewer
text/binary loaders in `src/app/viewer/component/viewer-utils.ts`. Viewer URLs
still come from the generated `getGetFileContentUrl` / `getDownloadFileUrl`
helpers. Both fetch paths preserve `ApiError` and dispatch the shared
`apsor-archive:unauthorized` event on `401`. Do not add other hand-written API
clients.

After a mutation, invalidate the related React Query keys (the pages use scoped
keys), so the dashboard, search, timeline, library, questions, chat, and memory
stay consistent.

## Chat

`/chat` and `/chat/:conversationId` render the persistent agent transcript. The
thread rail supports new, rename, archive/restore, and delete. The composer
streams over SSE with Cmd/Ctrl+Enter, a stop action, and a live turn view;
completed entries replace the optimistic view after the scoped query
invalidation. Markdown uses `react-markdown` + `remark-gfm` with `skipHtml`, and
citations open file previews in the File Library (`/library?tab=files&file=…`)
or memories in `/memory/…`; legacy `/viewer/*` links redirect there.

### Retry

`RetryBar` appears for the latest failed or cancelled assistant entry, a
trailing hard-limit tool result (`step_limit`, `token_limit`, `tool_call_limit`,
or legacy `tool_result_budget_exhausted` entries), or a stream failure before an assistant entry
was persisted. The decision lives in `readRetryState()` in `chat/types.ts`; an
ordinary tool error followed by a successful assistant answer is not retryable.

Retry calls `streamAgentRetry()` from `agent-stream.ts`, which posts to the
existing retry endpoint with only a generated `request_id`. It reuses the same
user entry, does not append a duplicate user message, and is disabled while a
stream is active. A `409 agent_run_not_retryable` response refetches the
transcript so the stale action disappears. A retry may hit the same token, step,
or tool-call budget again.

### Approval cards

`save_memory` is gated by a durable human approval. `ApprovalStack` in
`chat/component/ApprovalCard.tsx` is used by the chat workspace. It
loads `GET /api/v1/agent/conversations/{id}/approvals?status=pending`, so the
card reappears after a reload while the run is waiting. Each card shows the
proposed memory, supersedes/occurred-at context, write risk, and accessible
**Approve write** / **Reject** buttons with loading and error states. Resolution
streams through `streamAgentApproval()` (`agent-stream.ts`); duplicate or stale
resolutions surface the backend `409` and the approvals query refetches. The
composer is disabled while an approval is pending, and a stream that ends with
`run_end {status: "waiting"}` shows the waiting state instead of a generic
failure. The durable rows come from backend migration `f2b3c4d5e6a7`
(`agent_approval`).

### Compact and clear

The `/chat` thread toolbar exposes **Compact** and **Clear** through
`ContextActions`. Compact is immediate; Clear asks for one inline confirmation
because it changes the active model context. Both actions are disabled while a
stream is active and on archived threads. A `409 agent_conversation_busy`
response shows a stable message and refetches the thread; an archived thread
shows the archived error instead.

The returned `pi.compaction` or `pi.reset` entry is merged immediately and the
conversation is invalidated. `ContextBoundaryCard` renders either boundary as a
context card, not as a user question: it states that older transcript rows are
preserved in the reading view but hidden from the model's active context. The
compaction card shows the reason, folded-entry count, summary character count,
last user input, and an expandable summary. The reset card starts a new empty
active context.

### Forking

The thread rail exposes a **Fork** action on active conversations; archived
threads show the action disabled with an explanation to restore the thread
first. User and assistant entries expose **Fork from here**, which sends their
entry id as `at_entry_id` to the generated `useForkAgentConversation` hook.
Both paths show a toast, invalidate the conversation list, and navigate to
`/chat/{newId}`. A `409 agent_conversation_busy` or
`409 agent_conversation_archived` response is surfaced as an error and leaves
the current thread in place. Forked conversations show `Forked from #<id>` in
the masthead with a link to the source, and the rail labels them
`fork of #<id>`. Forking copies transcript entries only; runs, retry state, and
approval state are not copied.

Chat is the first item in the seven-item archive rail. The rail becomes a
navigation drawer below 980 px; the mobile bar opens it.

## Saved questions

`/questions` is the question book and a secondary page, linked from Search and
the method colophon. It uses the generated `useListSavedQuestions`,
`useCreateSavedQuestion`, `useUpdateSavedQuestion`, `useDeleteSavedQuestion`,
and `useAskSavedQuestion` hooks. No separate fetch client is added.

- **Create** — the composer accepts plain text up to 32,000 characters and
  sends only `question`. Creating a question does not create a conversation.
- **List and paginate** — the page requests 50 rows per page with
  `limit`/`offset`, shows `{resources, total, limit, offset}`, and offers
  Previous/Next with an explicit range. Deleting the last row on a page steps
  back one page.
- **Edit** — inline editing saves with `PATCH`. Changing the text clears the
  stored answer, citations, conversation link, run metadata, and last-asked
  time; the UI says so before saving and confirms the reset in a toast.
- **Delete** — a two-step inline confirmation calls `DELETE`; the row is removed
  from the cached page and the list is invalidated.
- **Ask** — **Ask agent** calls `POST .../ask` and waits for the returned saved
  question. This is one synchronous JSON request, not an SSE stream, so the
  card shows a pending message while the turn runs.
- **Result** — the returned row replaces the card in the list cache. A
  successful answer is rendered as text with `CitationChip` links for known
  citation tokens, a status badge, the last-asked time, and an **Open
  conversation** link to `/chat/{conversation_id}` when one exists.

After an ask, the page invalidates the saved-question list, the conversation
list, and (when present) the conversation detail and entry queries. A failed run
is still `200` from the API: the card shows `run_status="failed"` with its
`error_code`/`error_detail`, keeps the question, and shows an error toast. A
cancelled run is shown the same way. A missing AI configuration arrives as
`503 agent_not_configured` and is shown as an inline card error.

The page implements loading skeletons, an empty book state, a list-level retry
panel, an inline refresh error that preserves the current rows, a "past the
last page" recovery action, and per-card pending/error states. Ask, edit, and
delete are disabled while a card operation is in flight.

Mobile keeps the same card layout without horizontal overflow; the page is
reached through the navigation drawer.

## Chat workspace

`/chat` is a fixed-height three-column workspace: a collapsible conversations
drawer, the stream column, and a tool inspector. The 12 px separator supports
pointer drag, click-to-collapse, and keyboard arrows/Home/End; the ratio and
collapsed state persist in localStorage. Below 900 px the inspector becomes a
tab instead of a split. The composer sends on Enter, inserts a newline on
Shift+Enter, and exposes Stop while streaming.

There is no second composer. The former floating dock and command palette were
removed; saved questions run through `/chat` like any other conversation.

### Page context

The backend still accepts an optional `page_context` object with a turn, and the
transcript renders any persisted `pi.page-context` entry as a compact context
card through `readPageContextEntry()`. The current SPA does not attach a
snapshot: with the floating dock removed, Chat is the only composer and it skips
its own route. The API enforces the key/path/title/text limits and server-side
clipping.

### Expanded inspector

The inspector follows the newest tool call until the user pins a panel. It
offers **Follow current**, keeps the last valid resource visible when a later
tool has no resource, and reuses the existing file renderer and memory reader
rather than a second rendering stack.

The seven tools map to distinct panels: result constellation, manuscript chunks,
timeline band, folder branch map, memory chain, save receipt, specimen sheet, and
display stand. Every panel implements loading, empty, error, and success states,
and errors show the stable tool error code and the validated arguments.

Live `tool_end` events carry `entry_id`, `tool_call_id`, `name`, `status`,
`resource`, `data`, `duration_ms`, and `error_code`. `data` is the same UI-only
preview payload persisted on the `pi.tool-result` entry, so the live inspector
can render excerpts, tags, dimensions, memory previews, and viewer links
immediately. Provider-facing XML content is not reused as UI data.

`tool_start` and `tool_end` also include `parallel`, `batch_size`, and
`parallel_index`. The current `agent-stream.ts` normalizer keeps call identity
and result payload for rendering; it does not surface a separate parallel
badge. Transcript and tool-result order always follows assistant call order,
even when eligible calls execute through `asyncio.gather`.

The `save_memory` panel remains a wax-seal receipt for an appended memory. The
separate approval card is the human gate: the model cannot authorize a write, and
the UI asks the keeper to approve or reject before the tool runs. The **Require
manual approval for memory writes** setting (default on) controls future calls
only; when it is off, no approval card appears and the backend authorizes the
write directly. Pending cards created while the setting was on keep rendering
and still require an explicit decision.

The inspector panels are mounted by the chat workspace. The production build is
committed under `dist/`; rebuild and commit `dist/` (and `dist/pdfjs/` when it
changes) after frontend changes, because the Docker image does not run a
frontend build.

## Settings

`/settings` includes an **Agent runtime** panel (`settings/component/
AgentRuntimePanel.tsx`) backed by the generated `useGetAgentSettings`,
`useUpdateAgentSettings`, and `useResetAgentSettings` hooks. Provider/model
configuration remains in the existing AI provider panels.

The panel shows a Database/Defaults badge, the last `updated_at`, and a summary
with model context, turn budget, and compaction side by side. A token budget
meter shows the compaction threshold as a share of `max_total_tokens` with
remaining headroom. Every numeric field displays its default and valid range.
The thirteen runtime values are grouped into context budget, tool execution, and
compaction detail; auto compaction, parallel tools, and memory-write approval
are toggles.

The context budget group labels **Model context window** separately from
**Turn token budget** and **Auto-compaction threshold**. The context window is
provider/model metadata (default 1,000,000, range 8,000–2,000,000); changing it
never raises the 100,000-token turn budget or moves the 75,000-token compaction
threshold.

Validation happens before saving: integer/range checks plus the cross-field
rules (threshold below total tokens, parallel width within tool calls per turn).
Save is disabled for an invalid or unchanged draft. The server repeats
validation and the app maps failures to `400 invalid_request`; the panel shows
the returned detail inline.

The **Tool execution** group also has **Require manual approval for memory
writes**, an accessible switch that defaults to on. When on, a `save_memory`
request waits for the user's Approve/Reject decision. When off, no waiting run
or approval row is created: the backend authorizes the validated write directly
and the turn completes normally. This panel persists the preference and includes
it in dirty/reset/save behavior. The setting applies to new calls only; pending
approval cards created while it was on remain visible and still need an explicit
Approve/Reject.

Save sends a full thirteen-field `PUT`. **Reset defaults** uses a two-step
confirmation and persists the defaults through `POST .../settings/reset`; it is
not only a local form reset. The panel implements loading skeletons and an
inline error with a Retry action. Changes apply to new runs; an active SSE stream
keeps the immutable snapshot it started with.

### Ingestion runtime

The **Ingestion runtime** panel follows Agent runtime on `/settings`
(`settings/component/IngestRuntimePanel.tsx`) and is backed by the generated
`useGetIngestSettings`, `useUpdateIngestSettings`, and
`useResetIngestSettings` hooks. It edits the singleton `ingest_config` row, not
browser storage.

The panel shows a Database/Defaults badge, the last `updated_at`, and a short
summary of the active values. Six fields are grouped into **Worker** (poll
seconds, extract threads, max in-flight jobs, embedding concurrency) and
**Chunking** (target chars, overlap chars); each shows its default and valid
range. Validation runs before saving: whole-number and range checks plus the
rule that overlap must stay below the chunk target. Save is disabled for an
invalid or unchanged draft and sends a full six-field `PUT`. **Reset defaults**
uses a two-step confirmation and persists the defaults through the reset
endpoint.

A warning states that worker values apply to the next loop or job, and that
changing chunk sizes affects only future ingests; existing files must be
re-ingested before their chunk boundaries match. The server repeats validation
and maps failures to `400 invalid_request`.

## Folder workspace

`/library` is a folder-first board backed by `useReadPath`. The breadcrumb and
folder rail change the `path` query parameter; folder and file cards open the
next path or the existing reader. The `view` query parameter selects `board` or
`list`; board is the desktop default, while list is the default below 761 px and
remains the compact table fallback.

- **Board vs list** — the board is the default for folders and file cards; the
  list view keeps the compact metadata table. Both read the same `useReadPath`
  payload, so switching does not refetch a different contract.
- **New folder** — `NewFolderDialog` calls the generated `createFolder` hook and
  refreshes the current path. The backend creates missing ancestors and returns
  an existing folder idempotently; a path occupied by a file is a real `409`
  conflict shown as an error.
- **Drag upload** — files dropped from the desktop onto a folder card upload
  directly into that folder. The board rejects unsafe names and unsupported
  types before upload, enforces the 10 MB limit, and shows an intake tray with
  queued, uploading, processing, ready, and failed/rejected states. The same
  extension allowlist as `UploadDialog` applies in the browser and on the
  server.
- **Move** — a normal drop onto a folder moves the file. The board shows an
  explicit drop target and copy/move intent while dragging and invalidates the
  source and target paths after success. A move keeps the file id, so open
  viewers and citations stay valid.
- **Copy** — Alt/Option-drop or the explicit **Copy** action creates a new file
  id at version 1 with rebuilt chunks. Both records remain current.
- **Dialogs** — `MoveCopyDialog` is the touch and keyboard path; it accepts a
  destination folder and file name. `NewFolderDialog` creates a branch in place.
- **Batch move** — **Select** in the toolbar enters selection mode. Check any
  files, or use **Select all visible**, then choose **Move selected**. The action
  bar shows the count and stays outside the board and list, so the same flow
  works in both views. `BatchMoveDialog` sends the generated `moveFile` calls
  sequentially to one destination folder; each file is reported separately.
  Successful moves are kept when another file collides, failed files stay
  selected for a retry, and the page invalidates queries and summarises the
  result in toasts. Single-file move/copy, drag/drop, and Alt-drop are unchanged.
- **Conflicts and extensions** — a changed extension is `422 invalid_path`; an
  occupied target is `409 tree_path_conflict`. The board reports both without
  optimistic movement.
- **Mobile** — drag is never the only path. Each file card exposes **Move** and
  **Copy** actions from its menu, and the destination is chosen in the dialog.
  Selection mode and **Move selected** also work in the mobile list view, which
  is the default below 761 px. The layout must not overflow at 390 px.

### Ingestion progress

The upload dialog's file and text tabs call `useUploadFileAsync` and
`useCreateTextFileAsync`. Both return a durable job, and the page then polls
`getIngestJob` through `waitForIngestJob()` once per second until the job is
`ready` or `failed`. Progress is polled, not streamed over SSE.

`IngestProgress` is shared by the intake dialog and the drag-and-drop upload
tray. It shows the stage, a bar from `progress_pct`, and `Embedding x / y` from
`chunks_embedded` / `chunks_total`; queued, parsing, and chunking stay
indeterminate until a count exists. On failure the dialog shows
`error_detail` (or `error_code`) and offers **Retry ingest** through
`useRetryIngestJob`; the tray shows the failure message. When a dialog upload is
ready, the published file is fetched and opened; the tray invalidates the
library queries without hijacking the reader. Closing the dialog or leaving the
page stops local polling but does not cancel the durable job.

The progress UI lives in the intake dialog and the drag-and-drop tray; there are
no per-file ingestion cards on the library board.

The backend contract and status codes are documented in `backend/README.md`.
The board, dialogs, and generated folder/move/copy hooks are in the source tree
and the production `dist/` is rebuilt. The Docker image copies the committed
client and does not run a frontend build.

## Preview

Files open in an in-situ preview modal inside the File Library, with tabs for
page preview, chunk inspection, and metadata. Legacy `/viewer/*` URLs redirect
into the Library or the Memory reader, so deep links keep working:

- `/viewer/file/:fileId` → `/library?tab=files&file=…` — `react-pdf` 11 +
  `pdfjs-dist` 6.3.289 for PDF, `docx-preview` 0.4.1 in a script-disabled
  sandbox for DOCX, native image with `react-zoom-pan-pinch` 4.2.0, and an
  archive sheet for text/JSON/Markdown/CSV (`react-markdown` 10.1.0 +
  `remark-gfm` 4.0.1, `skipHtml`).
- `/viewer/media/:mediaId` → `/library?tab=media&media=…` — the same file
  preview for image files.
- `/viewer/memory/:memoryId` → `/memory/:memoryId` — the memory leaf with
  lineage and trace links.

Text-only files use `has_original=false`, skip the 404 **Open original** and
**Download** actions, skip the `/content` probe entirely, and rebuild the sheet
from indexed chunks. PDF.js CMaps and standard fonts are served from `/pdfjs/`
in the committed build.

## Design

The visual language is a herbarium / dendrochronology archive:

- warm paper, ink green, moss, vermilion, and ochre;
- Fraunces for display, IBM Plex Sans for UI, IBM Plex Mono for metadata;
- paper grain, tree rings, hairline rules, corner ticks;
- staggered page-load reveals, branch drawing, and a night archive dark theme.

All committed copy is English. Chinese text is supported as user content through
the CJK font fallbacks.

## Checks

```bash
bun run lint
bun run typecheck
bun run build
bun audit
```

The checks above cover type safety, linting, the production build, and
dependency audit. After frontend changes, rebuild and commit `dist/` (and
`dist/pdfjs/` when it changes) because the Docker image serves the committed
client and does not run a build. The `save_memory` receipt remains a record of
the write; the shared approval card is the human gate that authorizes it.
