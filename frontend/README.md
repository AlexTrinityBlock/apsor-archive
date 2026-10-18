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
    home/ search/ timeline/     route pages
    library/ tree/ memory/
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

The generated hooks cover normal JSON routes. Two deliberate exceptions use
same-origin `fetch` directly: `src/apis/agent-stream.ts` for
`text/event-stream`, and the viewer text/binary loaders in
`src/app/viewer/component/viewer-utils.ts`. Viewer URLs still come from the
generated `getGetFileContentUrl` / `getDownloadFileUrl` helpers. Both fetch paths
preserve `ApiError` and dispatch the shared `dendromatrix:unauthorized` event on
`401`. Do not add other hand-written API calls.

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
**Download** actions, and rebuild the sheet from indexed chunks. PDF.js CMaps
and standard fonts are served from `/pdfjs/` in the committed build.

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
