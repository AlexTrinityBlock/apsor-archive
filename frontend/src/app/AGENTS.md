# frontend/src/app/ — Agent Guide

The React application layer: route composition, providers, authentication, the application shell, shared visual primitives, and every archive workspace. Pages under this directory consume the generated API client and own their local components, hooks, and CSS.

## Purpose

- Compose the SPA from providers, routes, and lazy-loaded workspaces.
- Provide cross-workspace UI primitives and interaction patterns in `component/`.
- Hold the application-specific API client and committed Orval output.
- Keep each workspace's data flow, state, and presentation inside its own directory.

The application layer does not define backend behavior. API shapes come from `generated-apis-types/`, and every mutation must leave the React Query cache coherent for the surfaces that depend on it.

## Architecture

- **Provider order:** `providers.tsx` places `I18nProvider` outermost, then `QueryClientProvider`, `ToastProvider`, and `AuthProvider`. Auth screens, route errors, and toasts can therefore translate.
- **Routing:** `router.tsx` builds the browser router. `AuthGate` wraps all protected routes, `AppShell` supplies the rail/drawer shell, and page components are lazy imports with `Suspense` fallbacks. `/` redirects to `/chat` before the shell mounts so the layout never captures a stale `/` location.
- **Navigation:** the shell is grouped. Main: Chat, Library, Timeline, Search, Dashboard. Memories are the Library's third tab (`/library/memories`), not a separate workspace. Personal: User profile. System: Settings, Change password, Accounts (root only), About. Session: Sign out. The Change password item opens the shared dialog. The footer identity is the root-only entry into `ImpersonateUserDialog` when root is not impersonating; other states show a plain identity block. While impersonating, the footer keeps the target account and a **Viewing as** marker, and a banner above the page canvas names the target with **Return to root**, which opens `StopImpersonationDialog` for root re-authentication. The personal block sits above Settings and is separate from the footer account card. The rail collapses on desktop and becomes a drawer below 980 px; opening the footer switcher closes the drawer. `/questions` (saved questions) and `/change-password` are routed pages outside the nav: the Change password nav item opens the dialog, while the page serves deep links.
- **Data:** pages call generated React Query hooks, which call `apiFetch`. The shared client uses 30-second staleness, one retry, and no refetch on window focus. Mutations use scoped invalidation; do not use a global cache reset for routine refreshes.
- **Workspaces:** each page lives in `<workspace>/page.tsx` with page-specific `component/`, `hook/`, and `<workspace>.css` (the Dashboard is `dashboard/`; About still uses `about/method.css`). `agent/` and `viewer/` are supporting domains rather than navigation entries: the first feeds chat inspection, the second renders files in the Library, chat, and the agent inspector. `auth/` is also consumed by accounts, settings, and chat.
- **Boundaries:** `scripts/check-boundaries.ts` (`bun run check:boundaries`) fails on a new cross-workspace import. Its documented exceptions are the `agent` ↔ `chat` pair (shared run types and renderers), `auth` → `chat/session-storage` (sign-out clears the last-chat pointer), `timeline` → `memory` dialogs and `memory` → the Settings `ConfirmDialog` re-export (both removed by the memory merge), and `questions` → `chat` citation helpers.
- **Shared layer:** `component/` contains only cross-page primitives such as `AppShell`, `PageHeader`, `Panel`, `Button`, `QueryState`, `Toast`, `ContextMenu`, `SearchField`, and icon/ring primitives. `ConfirmDialog` is the shared confirmation modal. `hook/` contains general hooks such as scroll lock, debounced values, drawer focus handling, and the app-level visual-viewport tracker that `AppShell` owns. `type/` holds local UI types (`ui.ts`).
- **Fixed canvases:** `AppShell` gives Chat and Library a fixed-height `.app-page--fixed`; other routes use the normal scrolling `.app-page`. The impersonation banner sits above that canvas as a flex-shrink-0 row, so fixed pages keep their own scroll owner. The page canvas is keyed by current user id plus impersonation actor id, so a same-tab account switch remounts the workspace and drops drafts/dialog state. Pages should not fight those scroll owners.
- **Legacy URLs:** `/ask`, `/tree`, `/overview` (→ `/dashboard`), `/docs` and `/method` (→ `/about`), `/media` (→ `/library/media`), `/memory/*` (→ `/library/memories/*`, keeping query and navigation state), `/viewer/*`, and old query-string `/library?path=...&file=...` links redirect to their canonical destinations. Keep route-table redirects in the router; Library URLs canonicalize inside `LibraryPage` before its state hooks mount.

## Key files

- `../main.tsx` — browser entry; global CSS, providers, and router.
- `providers.tsx` — provider composition and ordering.
- `router.tsx` — lazy route table, auth gate, shell, and redirects.
- `query-client.ts` — shared TanStack Query defaults.
- `component/AppShell.tsx` — rail, mobile drawer, health status, root user switcher entry, impersonation banner, session actions, and page canvas.
- `component/RouteError.tsx` — root error boundary with one stale-chunk reload guard.
- `component/QueryState.tsx` — shared loading, error, and empty frame.
- `component/ContextMenu.tsx` — portal menu with viewport flipping and keyboard navigation.
- `auth/AuthGate.tsx`, `auth/AuthProvider.tsx`, and `auth/RequireRoot.tsx` — setup/login/logout and impersonation session state, forced password change, role helpers, and the `apsor-archive:unauthorized` listener. A lost/disabled session clears the entire React Query cache before returning to the gate; login, impersonation start, impersonation stop, logout, and unauthorized handling also clear the last-chat pointer. `AuthProvider` broadcasts transitions to other tabs and observes status-refetch identity changes as defence in depth. `RequireRoot` sends an impersonation target from `/accounts` to `/chat` rather than the normal-user `/profile` fallback.
- `auth/component/ImpersonateUserDialog.tsx` — root-only searchable user switcher; excludes root and the current account, blocks disabled/forced-password targets, and traps focus.
- `auth/component/StopImpersonationDialog.tsx` — root-password re-authentication dialog for returning to a fresh root session.
- `auth/session-transition.ts` — BroadcastChannel primary / localStorage fallback transition bus that reloads other tabs after an auth change.
- `accounts/page.tsx` / `accounts/component/AccountCard.tsx` — root-only account directory with identity, dates, rolled-up token/API/turn usage, safe actions, and the impersonation confirmation.
- `generated-apis-types/` — committed Orval hooks, URLs, query keys, and schemas. Never edit by hand.
- `viewer/component/viewer-utils.ts` — the approved non-JSON fetch path for viewer content.
- `library/AGENTS.md`, `settings/AGENTS.md`, `i18n/AGENTS.md` — focused guides for the largest application areas.

## Conventions

- A new workspace gets its own directory, a `page.tsx` with a named page export, page-specific subdirectories, and a lazy route entry in `router.tsx`.
- Do not import a page-specific component from another workspace. Promote a truly shared primitive to `app/component/` instead.
- Use generated query hooks and generated query-key helpers. Invalidate only affected paths, stats, timeline, search, file, or conversation keys.
- Do not add a new `fetch` call. Route JSON through `apiFetch`; the existing SSE and viewer loaders are deliberate exceptions. The chat-image upload in `chat/attachments.ts` is the deliberate XHR exception because only `xhr.upload.onprogress` reports portable upload progress and only `xhr.abort()` cancels the request.
- Keep browse/dialog state in the URL when it should survive refresh, and keep ephemeral UI state local. Do not mirror the same state in both.
- Translate every string through `useI18n`; keep labels and ARIA text out of JSX literals.
- Reuse `Button`, `Panel`, `PageHeader`, `EmptyState`, `QueryState`, `Toast`, and `ContextMenu` rather than cloning their behavior.
- Impersonation is a session transition, not page state. Call `useAuth().impersonate` / `stopImpersonation(password)`; never set auth status by hand or keep target/root private rows in the query cache across the switch. Other tabs reload by design, and same-tab workspaces remount through the keyed page canvas.
- New dialogs and menus must manage focus, Escape, keyboard traversal, and focus return. New icons belong in `component/Icon.tsx`.
- Page CSS is imported by that page or its owning component and uses a workspace prefix. Global tokens and shell rules belong in `src/styles/`.

## Chat workspace

- Every persisted assistant step and its immediately following tool results render in transcript order. Do not fold linked `pi.tool-result` entries out of the reading view, merge assistant steps into one bubble, or render only the last step.
- The live stream keeps an ordered segment list: assistant prose for one step, then that step's tools, then the next assistant step. A new `message_start` appends a segment; it never erases earlier prose.
- Tool steps show their concrete arguments and a bounded structured preview. The model-facing tool XML is never rendered, and hidden provider reasoning is not invented when the contract does not persist it.
- Tool steps and thinking blocks preserve every recorded detail. Arguments, text previews, and error detail stay collapsed by default, including live steps, together with the agent's reasoning. Charts and presented resources (images, documents, memory cards) render expanded above the disclosure with a large preview area because they are the model's output to the reader. The always-visible tool header and meta line keep status, duration, call id, and error code readable while the disclosure is closed.
- A presented file carries its server thumbnail (`resource.thumbnail`: version, width, height). `ResourceCard` uses it to fix the preview box size before any byte loads and paints the tiny WebP first: images fade the original in over it, PDFs draw the pdf.js canvas over it at the same size, and other kinds show it instead of the type tile. The preview dialog and `FileRenderer` use the same thumbnail as their loading state. Older transcripts without a thumbnail keep the previous behaviour.
- A live tool step is isolated from assistant prose tokens. Streaming a token must not re-render or remount a presented PDF, chart, or resource card; keep the live step memoized and its callbacks stable so the preview stays on screen.
- Fenced code blocks in the transcript offer one-click copy of the raw code text; inline backtick code has no copy control.
- Inline charts enable Plotly `automargin` on every cartesian axis. A chart whose long category labels cannot fit the reading column gets a minimum width and scrolls horizontally inside its card instead of compressing labels into each other; the scroll hint appears only while the canvas overflows.
- Scroll follow lives in `chat/hook/useStickToBottom.ts` (pure rules in `chat/scroll-follow.ts`): pin in a layout effect, re-pin on `ResizeObserver` growth, detach on any upward intent, re-attach only near the end, and show **Jump to latest** when detached. Do not reintroduce a post-paint `scrollTop` effect.
- The live-turn reducer is pure (`chat/hook/stream-reducer.ts`); token deltas are batched per animation frame and any structural event flushes first. Keep new event handling in the reducer with a `bun:test` case.
- Leaving the page or switching threads while a run streams asks first (`useBlocker` + `LeaveRunDialog`), because a disconnect stops the run server-side. Hash-only and same-path navigations pass.
- Presented resources reserve their final box before loading. `ResourceThumb` picks server thumbnail → image original → PDF page 1 → type tile; its `thumbnail` prop is the seam for server-rendered thumbnails.
- Composer drafts are kept per conversation in memory only (`chat/draft-map.ts`); never persist them.
- On mobile the fixed chat shell follows the visual viewport while the on-screen keyboard is open, so the transcript top and the composer stay reachable. The inner transcript remains the scroll owner; do not replace this with scroll padding or by letting the page body scroll.

## Verification

```bash
cd frontend
bun run lint
bun run typecheck
bun run i18n:check
bun run check:boundaries
bun run test
bun run build
```

Exercise the route at desktop and mobile widths, including browser back/forward when the page writes query or hash state.

## Related guides

- [Frontend](../../AGENTS.md)
- [Library](./library/AGENTS.md)
- [Settings](./settings/AGENTS.md)
- [Internationalization](./i18n/AGENTS.md)
- [Global styles](../styles/AGENTS.md)
