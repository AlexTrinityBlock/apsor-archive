# DendroMatrix Frontend

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
    hook/                       theme, command palette, debounce
    type/                       UI types and local demo shapes
    agent/                      global dock, page context, inspector panels
    home/ search/ timeline/     route pages
    library/                    folder workspace board + list view
    tree/ memory/
    chat/                       persistent agent reading room
    viewer/                     file/media/memory viewers
    ask/ method/ settings/
  lib/                          formatting, safe text highlighting
  styles/                       paper / night archive design tokens
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
`moveFile`, and `copyFile`. Two deliberate exceptions use same-origin `fetch`
directly: `src/apis/agent-stream.ts` for `text/event-stream`, and the viewer
text/binary loaders in `src/app/viewer/component/viewer-utils.ts`. Viewer URLs
still come from the generated `getGetFileContentUrl` / `getDownloadFileUrl`
helpers. Both fetch paths preserve `ApiError` and dispatch the shared
`dendromatrix:unauthorized` event on `401`. Do not add other hand-written API
clients.

After a mutation, invalidate the related React Query keys (the pages use
`queryClient.invalidateQueries()`), so the overview, search, timeline, tree,
library, chat, and viewer stay consistent.

## Chat

`/chat` and `/chat/:conversationId` render the persistent agent transcript. The
thread rail supports new, rename, archive/restore, and delete. The composer
streams over SSE with Cmd/Ctrl+Enter, a stop action, and a live turn view;
completed entries replace the optimistic view after the scoped query
invalidation. Markdown uses `react-markdown` + `remark-gfm` with `skipHtml`, and
citations become viewer links only for `/viewer/file|media|memory/...`.

Chat is in the **Studio** sidebar and the command palette. Mobile bottom tabs
stay Overview, Search, Timeline, Library, and More; Chat is reached through the
navigation drawer.

## Agent dock

`AgentDock` is mounted inside `AppShell` but outside `<main>`, so it persists
across archive routes and is explicitly excluded from page-context capture. It
is intentionally hidden on `/chat`, which keeps the full-page desk as the
single composer for that route. The dock has three states:

- `collapsed` — a floating seal/button in the lower-right corner;
- `panel` — a compact chat panel with recent conversations, the live stream, and
  the composer;
- `expanded` — a full-screen split workspace with the conversation on the left
  and the tool inspector on the right.

The state is kept in localStorage under the dock's own key, and the selected
conversation id is remembered separately. Expanding from the panel opens the
current conversation in the split view; `/chat` remains the full-page desk and
uses the same conversation id. On mobile, `collapsed` opens a full-height sheet;
the expanded surface switches to Correspondence / Workbench pane tabs, and the
layout must not produce horizontal overflow.

### Page context

`app/agent/page-context.ts` captures a plain-text snapshot of `#main-content`:

- only the main column is read; `nav`, form controls, hidden nodes,
  `aria-hidden` nodes, `[data-agent-surface]` (the dock), and
  `[data-page-context='exclude']` are skipped;
- block elements contribute paragraph breaks, and repeated whitespace is
  compacted;
- `/chat` and `/chat/:conversationId` are skipped because the desk is the
  conversation itself; viewer routes are outside `AppShell` and have no
  `#main-content`, so they produce no snapshot;
- the key is `v1:<pathname>` plus canonical, meaningful query parameters
  (`path`, `file`, `chunk`, `q`, timeline filters, and similar), so irrelevant
  parameters do not manufacture a new page identity;
- the title is capped at 300 characters and the plain text at 6,000 characters.

`usePageContext` captures once on route change and debounces MutationObserver
updates by 220 ms so async page loads settle into one snapshot. The composer
receives the current snapshot through `useChatStream.start(conversationId,
content, pageContext)` and shows an expandable **Current page context** preview.
The transcript reads persisted `pi.page-context` entries through
`readPageContextEntry()` and renders a compact context card; it must not count
as a user question. `lastPageContextKey()` reads the detail field for reload
continuity while the backend remains the source of truth for deduplication.

### Expanded inspector

The inspector follows the newest tool call until the user pins a panel. It
offers **Follow current**, keeps the last valid resource visible when a later
tool has no resource, and reuses the existing file renderer plus the media and
memory viewer queries rather than a second rendering stack.

The nine tools map to distinct panels: result constellation, manuscript chunks,
timeline band, folder branch map, memory chain, save receipt, media contact
sheet, specimen sheet, and display stand. Every panel implements loading, empty,
error, and success states, and errors show the stable tool error code and the
validated arguments.

Live `tool_end` events carry `entry_id`, `tool_call_id`, `name`, `status`,
`resource`, `data`, `duration_ms`, and `error_code`. `data` is the same UI-only
preview payload persisted on the `pi.tool-result` entry, so the live inspector
can render excerpts, tags, dimensions, memory previews, and viewer links
immediately. Provider-facing XML content is not reused as UI data.

The `save_memory` panel is a wax-seal receipt for an appended memory. It is not
a human approval dialog: the `user_confirmed=true` flag is still model-supplied
and prompt-enforced, and the UI does not ask the keeper to approve a write.

`AgentDock` and the inspector panels are mounted by `AppShell` on archive pages.
The production build is committed under `dist/`; rebuild and commit `dist/` (and
`dist/pdfjs/` when it changes) after frontend changes, because the Docker image
does not run a frontend build.

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
  queued, uploading, archived, and rejected states. The same extension
  allowlist as `UploadDialog` applies in the browser and on the server.
- **Move** — a normal drop onto a folder moves the file. The board shows an
  explicit drop target and copy/move intent while dragging and invalidates the
  source and target paths after success. A move keeps the file id, so open
  viewers and citations stay valid.
- **Copy** — Alt/Option-drop or the explicit **Copy** action creates a new file
  id at version 1 with rebuilt chunks. Both records remain current.
- **Dialogs** — `MoveCopyDialog` is the touch and keyboard path; it accepts a
  destination folder and file name. `NewFolderDialog` creates a branch in place.
- **Conflicts and extensions** — a changed extension is `422 invalid_path`; an
  occupied target is `409 tree_path_conflict`. The board reports both without
  optimistic movement.
- **Mobile** — drag is never the only path. Each file card exposes **Move** and
  **Copy** actions from its menu, and the destination is chosen in the dialog.
  The layout must not overflow at 390 px.

The backend contract and status codes are documented in `backend/README.md`.
The board, dialogs, and generated folder/move/copy hooks are in the source tree
and the production `dist/` is rebuilt. The Docker image copies the committed
client and does not run a frontend build.

## Viewer

The viewer routes live under `AuthGate` as siblings of `AppShell`, so they keep
deep links, new tabs, their own top bar, and safe-area layout:

- `/viewer/file/:fileId` — `react-pdf` 11 + `pdfjs-dist` 6.3.289 for PDF,
  `docx-preview` 0.4.1 in a script-disabled sandbox for DOCX, native image with
  `react-zoom-pan-pinch` 4.2.0, and an archive sheet for text/JSON/Markdown/CSV
  (`react-markdown` 10.1.0 + `remark-gfm` 4.0.1, `skipHtml`).
- `/viewer/media/:mediaId` — native image + zoom/pan, notes, and a
  `yet-another-react-lightbox` 3.32.2 gallery.
- `/viewer/memory/:memoryId` — the memory leaf with lineage and trace links.

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

Current validation: typecheck, lint, build, and
audit pass; the committed `dist/` is the rebuilt production client. Playwright
passed 34 deterministic checks at 1440×1000 and 390×844, covering the dock
states, page-context dedupe, workspace move/copy/upload, and mobile pane
switching. A focused re-check then passed 6/6: multi-chunk search keys,
text-only `/content` behavior, stored-original loading, legacy-404 fallback,
390px Workbench tabs, and the `save_memory` wax-seal receipt. The receipt is
still not a human approval dialog.
