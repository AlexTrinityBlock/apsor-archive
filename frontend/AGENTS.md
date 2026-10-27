# frontend/ — Agent Guide

Apsor Archive's React single-page application. This directory owns the browser UI, the typed API client generated from the committed OpenAPI schema, the local design system, static fonts, and the production build served by FastAPI.

## Purpose

- Implement every archive workspace and shared interaction in the browser.
- Enforce the root/user surface in the shell: root-only Accounts and global Settings tabs, a private personal block, a forced change-password gate, and a visible impersonation banner with a return-to-root action.
- Keep the UI aligned with the committed FastAPI contract in `openapi.json`.
- Ship a reproducible static bundle under `dist/`; the Docker image compiles it in a Bun stage and the runtime image serves the result.
- Own frontend-only concerns: routing, query caching, i18n, accessibility, responsive layout, PDF.js runtime assets, and visual tokens.

It does not own backend behavior, database migrations, API schemas, or deployment configuration. Change the backend contract first, then export OpenAPI and regenerate the client. Hiding a route or nav item is convenience, never the security boundary; the backend independently returns `403` for non-root or cross-account access.

## Architecture

- **Toolchain:** Bun 1.3.6, React 19, Vite 8, TypeScript 5.9 in strict mode, React Router 7, TanStack Query 5, and Orval 8. There is no Tailwind, CSS-in-JS, or component library.
- **Boot:** `src/main.tsx` imports `styles/index.css`, mounts `AppProviders`, then renders `RouterProvider`. `AppProviders` nests i18n outermost, then React Query, toasts, and auth.
- **Auth:** `AuthProvider` resolves `/auth/status` into `user`, `role`, `isRoot`, `mustChangePassword`, and the optional `impersonation` actor. `isRoot` follows the current session, so it is false while root is impersonating a normal user. `AuthGate` orders loading → load error → setup → login → blocking change-password screen → authenticated outlet. `RequireRoot` guards `/accounts` and redirects a normal user to `/profile`, or an impersonation target to `/chat`. Login, impersonation start, impersonation stop, logout, and unauthorized handling clear private query data and the last-chat pointer before installing the new auth-status snapshot. Stopping impersonation re-authenticates with the root password; other tabs receive a BroadcastChannel/localStorage transition and reload so stale account DOM and query rows cannot survive. A status refetch that observes a different user id clears rows and confirms once.
- **Routing:** `src/app/router.tsx` uses `createBrowserRouter` with a root `AuthGate`, the `AppShell` layout, and lazy page imports. `/` redirects to `/chat`; legacy viewer routes redirect into the Library or Memory reader.
- **Navigation:** `AppShell` renders four groups: archive workspaces, a personal block with User profile, a system block with Settings, Change password, Accounts (root only), and About, then a Session block with Sign out. The Change password item opens the dialog. The footer identity is a root-only button into `ImpersonateUserDialog` when not already impersonating; normal accounts and impersonation targets see a plain identity block. While impersonating, a banner above the page canvas names the target and exposes Return to root, which opens `StopImpersonationDialog` for root re-authentication. Visible indices are computed after role filtering.
- **API access:** generated Orval hooks call `src/apis/fetch-client.ts`, which uses same-origin relative URLs and throws `ApiError`. Vite proxies `/api` and `/health` to the backend in development.
- **Build output:** `dist/` is generated and gitignored, built by the Docker image and by `bun run build` for a local preview. `public/pdfjs/` is generated and gitignored too.
- **PDF.js assets:** `scripts/copy-pdfjs-assets.mjs` copies CMaps and standard fonts from the pinned `pdfjs-dist` package. `dev` and `build` run it automatically.

## Key files

- `package.json` — scripts, pinned runtime dependencies, and Bun package manager version.
- `vite.config.ts` — development proxy, fixed dev/preview hosts, and `dist` output.
- `tsconfig.app.json` — strict application compiler settings; unused locals and parameters fail.
- `eslint.config.js` — React hooks, security, sanitization, JSDoc, and Sonar rules.
- `orval.config.ts` — tags-split React Query generation into `src/app/generated-apis-types/`.
- `openapi.json` — committed FastAPI schema used when no backend is running.
- `src/apis/fetch-client.ts` — shared JSON mutator and `ApiError` contract.
- `src/apis/agent-stream.ts` — the deliberate SSE exception for agent turns.
- `src/app/auth/AuthProvider.tsx` / `AuthGate.tsx` / `RequireRoot.tsx` — session state, impersonation transitions, first-run and forced-change gates, root route guard.
- `src/app/auth/component/ChangePasswordScreen.tsx` — non-dismissible forced password change.
- `src/app/auth/component/ImpersonateUserDialog.tsx` — root-only searchable user switcher with focus trap and busy blocking.
- `src/app/auth/component/StopImpersonationDialog.tsx` — root-password re-authentication before returning to a fresh root session.
- `src/app/auth/session-transition.ts` — BroadcastChannel/localStorage notification that reloads other tabs after an auth transition.
- `src/app/accounts/page.tsx` — root-only account directory, usage cards, impersonation action, and one-time temporary-password dialogs.
- `src/app/settings/component/settings-sections.ts` — role-filtered Settings tab registry.
- `src/app/viewer/component/viewer-utils.ts` — deliberate text/binary viewer fetch exception; URLs still come from generated helpers.
- `scripts/check-i18n.ts` — locale key-parity check against English.
- `dist/` — generated production bundle, including `dist/pdfjs/`; never edit by hand.

## Conventions

- Use Bun and the existing scripts. Do not introduce npm, pnpm, or a second lockfile.
- Do not edit `src/app/generated-apis-types/`; regenerate with `bun run api:generate`. Generated code is ignored by ESLint for a reason.
- Do not add hand-written API clients. The only exceptions are the existing SSE stream and viewer text/binary loaders. Both preserve `ApiError` behavior and dispatch `apsor-archive:unauthorized` on `401`.
- After mutations, invalidate the narrow React Query keys that changed. Avoid blanket invalidation except for deliberate seeding. Account create/disable/enable/reset invalidates the account list; patch or invalidate auth status only when the current account changes. Impersonation start and stop must use `useAuth().impersonate` / `stopImpersonation`: `AuthProvider` replaces the auth-status snapshot, clears every private query, and broadcasts the transition so root and target rows never survive in this tab or another tab. Stopping requires the root password and must not navigate from inside the provider.
- Keep a one-time temporary password in local dialog state only. Never place it in the React Query cache, localStorage, a URL, a log, or a toast; clear it when the dialog closes.
- Derive role visibility from `useAuth` (`isRoot`) and the Settings section `roles` field. Hidden deep links fall back to the first visible Settings tab, and a direct `/accounts` visit redirects a normal user to `/profile`.
- All interface copy goes through `src/app/i18n`; add keys to English and both Chinese locales. Never hardcode user-facing labels, ARIA text, toasts, or errors.
- Every workspace owns its `page.tsx`, `component/`, `hook/`, and page CSS. Only reusable primitives belong in `src/app/component/`.
- Prefer the design tokens and shared primitives in `src/styles/` and `src/app/component/`. Do not add a second styling system.
- Keep TypeScript strict: no `any`, use type-only imports, and preserve the security and sanitization lint rules.
- Never hand-edit `dist/`; the Docker build rebuilds it from source. Run `bun run build` only when you need a local preview.

## Verification

```bash
cd frontend
bun run lint
bun run typecheck
bun run i18n:check
bun run build
```

A successful build writes `dist/` and the generated PDF.js assets to the working tree; both are gitignored, so commit only the source changes.

## Related guides

- [Repository](../AGENTS.md)
- [Application layer](./src/app/AGENTS.md)
- [Global styles](./src/styles/AGENTS.md)
