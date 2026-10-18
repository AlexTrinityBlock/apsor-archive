# DendroMatrix Frontend

React 19 + TypeScript + Vite single-page archive. The production build is
committed under `dist/` and served by FastAPI.

## Scripts

```bash
bun install
bun run dev          # Vite on 127.0.0.1:5173, proxies /api to :8000
bun run build        # tsc -b && vite build
bun run typecheck
bun run lint
bun run api:generate # Orval, requires the API at :8000
```

## Structure

```text
src/
  apis/fetch-client.ts          single fetch mutator; throws ApiError
  app/
    component/                  shared shell, panels, badges, toast
    generated-apis-types/       committed Orval client
    hook/                       theme, command palette, debounce
    type/                       UI types and local demo shapes
    home/ search/ timeline/     route pages
    library/ tree/ memory/
    ask/ method/ settings/
  lib/                          formatting, safe text highlighting
  styles/                       paper / night archive design tokens
```

Each page owns its components under `<page>/component/` and its page-specific
CSS under `<page>/<page>.css`. Shared visual primitives live in
`app/component/`; the design tokens live in `styles/tokens.css`.

## API generation

Orval reads the FastAPI OpenAPI schema:

```bash
# backend running on :8000
bun run api:generate
```

The generated hooks are the only API call surface. Do not hand-write `fetch`
calls outside `src/apis/fetch-client.ts`. After a mutation, invalidate the
related React Query keys (the pages use `queryClient.invalidateQueries()`), so
the overview, search, timeline, tree, and library stay consistent.

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
