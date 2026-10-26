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
- **Navigation:** the shell is grouped. Main: Chat, Library, Timeline, Memory, Search, Dashboard. Personal: User profile. System: Settings, Change password, Accounts (root only), About. Session: Sign out. The Change password item opens the shared dialog. The footer account card shows identity only. The personal block sits above Settings and is separate from the footer account card. The rail collapses on desktop and becomes a drawer below 980 px.
- **Data:** pages call generated React Query hooks, which call `apiFetch`. The shared client uses 30-second staleness, one retry, and no refetch on window focus. Mutations use scoped invalidation; do not use a global cache reset for routine refreshes.
- **Workspaces:** each page lives in `<workspace>/page.tsx` with page-specific `component/`, `hook/`, and `<workspace>.css`. `agent/` and `viewer/` are supporting domains rather than navigation entries: the first feeds chat inspection, the second renders files in the Library and chat.
- **Shared layer:** `component/` contains only cross-page primitives such as `AppShell`, `PageHeader`, `Panel`, `Button`, `QueryState`, `Toast`, `ContextMenu`, `SearchField`, and icon/ring primitives. `hook/` contains general hooks such as scroll lock and debounced values. `type/` holds local UI types.
- **Fixed canvases:** `AppShell` gives Chat and Library a fixed-height `.app-page--fixed`; other routes use the normal scrolling `.app-page`. Pages should not fight those scroll owners.
- **Legacy URLs:** `/ask`, `/tree`, `/overview`, `/docs`, and `/viewer/*` redirect in the router. Keep redirects in the route table, not inside page components.

## Key files

- `../main.tsx` — browser entry; global CSS, providers, and router.
- `providers.tsx` — provider composition and ordering.
- `router.tsx` — lazy route table, auth gate, shell, and redirects.
- `query-client.ts` — shared TanStack Query defaults.
- `component/AppShell.tsx` — rail, mobile drawer, health status, account actions, and page canvas.
- `component/RouteError.tsx` — root error boundary with one stale-chunk reload guard.
- `component/QueryState.tsx` — shared loading, error, and empty frame.
- `component/ContextMenu.tsx` — portal menu with viewport flipping and keyboard navigation.
- `auth/AuthGate.tsx` and `auth/AuthProvider.tsx` — setup/login/logout session state, forced password change, role helpers, and the `apsor-archive:unauthorized` listener. A lost/disabled session clears the entire React Query cache before returning to the gate; login does the same so one account's cached rows never survive into another session.
- `generated-apis-types/` — committed Orval hooks, URLs, query keys, and schemas. Never edit by hand.
- `viewer/component/viewer-utils.ts` — the approved non-JSON fetch path for viewer content.
- `library/AGENTS.md`, `settings/AGENTS.md`, `i18n/AGENTS.md` — focused guides for the largest application areas.

## Conventions

- A new workspace gets its own directory, a `page.tsx` with a named page export, page-specific subdirectories, and a lazy route entry in `router.tsx`.
- Do not import a page-specific component from another workspace. Promote a truly shared primitive to `app/component/` instead.
- Use generated query hooks and generated query-key helpers. Invalidate only affected paths, stats, timeline, search, file, or conversation keys.
- Do not add a new `fetch` call. Route JSON through `apiFetch`; the existing SSE and viewer loaders are deliberate exceptions.
- Keep browse/dialog state in the URL when it should survive refresh, and keep ephemeral UI state local. Do not mirror the same state in both.
- Translate every string through `useI18n`; keep labels and ARIA text out of JSX literals.
- Reuse `Button`, `Panel`, `PageHeader`, `EmptyState`, `QueryState`, `Toast`, and `ContextMenu` rather than cloning their behavior.
- New dialogs and menus must manage focus, Escape, keyboard traversal, and focus return. New icons belong in `component/Icon.tsx`.
- Page CSS is imported by that page or its owning component and uses a workspace prefix. Global tokens and shell rules belong in `src/styles/`.

## Verification

```bash
cd frontend
bun run lint
bun run typecheck
bun run i18n:check
bun run build
```

Exercise the route at desktop and mobile widths, including browser back/forward when the page writes query or hash state.

## Related guides

- [Frontend](../../AGENTS.md)
- [Library](./library/AGENTS.md)
- [Settings](./settings/AGENTS.md)
- [Internationalization](./i18n/AGENTS.md)
- [Global styles](../styles/AGENTS.md)
