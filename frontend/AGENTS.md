# frontend/ — Agent Guide

Apsor Archive's React single-page application. This directory owns the browser UI, the typed API client generated from the committed OpenAPI schema, the local design system, static fonts, and the production build served by FastAPI.

## Purpose

- Implement every archive workspace and shared interaction in the browser.
- Enforce the root/user surface in the shell: root-only Accounts and global Settings tabs, a private personal block, and a forced change-password gate.
- Keep the UI aligned with the committed FastAPI contract in `openapi.json`.
- Ship a reproducible static bundle under `dist/`; the production image serves this bundle and does not run a frontend build.
- Own frontend-only concerns: routing, query caching, i18n, accessibility, responsive layout, PDF.js runtime assets, and visual tokens.

It does not own backend behavior, database migrations, API schemas, or deployment configuration. Change the backend contract first, then export OpenAPI and regenerate the client. Hiding a route or nav item is convenience, never the security boundary; the backend independently returns `403` for non-root or cross-account access.

## Architecture

- **Toolchain:** Bun 1.3.6, React 19, Vite 8, TypeScript 5.9 in strict mode, React Router 7, TanStack Query 5, and Orval 8. There is no Tailwind, CSS-in-JS, or component library.
- **Boot:** `src/main.tsx` imports `styles/index.css`, mounts `AppProviders`, then renders `RouterProvider`. `AppProviders` nests i18n outermost, then React Query, toasts, and auth.
- **Auth:** `AuthProvider` resolves `/auth/status` into `user`, `role`, `isRoot`, and `mustChangePassword`. `AuthGate` orders loading → load error → setup → login → blocking change-password screen → authenticated outlet. `RequireRoot` guards `/accounts` and redirects a normal user to `/profile`.
- **Routing:** `src/app/router.tsx` uses `createBrowserRouter` with a root `AuthGate`, the `AppShell` layout, and lazy page imports. `/` redirects to `/chat`; legacy viewer routes redirect into the Library or Memory reader.
- **Navigation:** `AppShell` renders three groups: archive workspaces, a personal block with User profile, then Settings, Change password, Accounts (root only), and About. The Change password item opens the footer dialog. Footer content is account identity plus Change password and a labeled Sign out action. Visible indices are computed after role filtering.
- **API access:** generated Orval hooks call `src/apis/fetch-client.ts`, which uses same-origin relative URLs and throws `ApiError`. Vite proxies `/api` and `/health` to the backend in development.
- **Build output:** `dist/` is tracked and committed. `public/pdfjs/` is generated and gitignored, while the emitted `dist/pdfjs/` is committed for the Docker image.
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
- `src/app/auth/AuthProvider.tsx` / `AuthGate.tsx` / `RequireRoot.tsx` — session state, first-run and forced-change gates, root route guard.
- `src/app/auth/component/ChangePasswordScreen.tsx` — non-dismissible forced password change.
- `src/app/accounts/page.tsx` — root-only account directory and one-time temporary-password dialogs.
- `src/app/settings/component/settings-sections.ts` — role-filtered Settings tab registry.
- `src/app/viewer/component/viewer-utils.ts` — deliberate text/binary viewer fetch exception; URLs still come from generated helpers.
- `scripts/check-i18n.ts` — locale key-parity check against English.
- `dist/` — committed production bundle, including `dist/pdfjs/`.

## Conventions

- Use Bun and the existing scripts. Do not introduce npm, pnpm, or a second lockfile.
- Do not edit `src/app/generated-apis-types/`; regenerate with `bun run api:generate`. Generated code is ignored by ESLint for a reason.
- Do not add hand-written API clients. The only exceptions are the existing SSE stream and viewer text/binary loaders. Both preserve `ApiError` behavior and dispatch `apsor-archive:unauthorized` on `401`.
- After mutations, invalidate the narrow React Query keys that changed. Avoid blanket invalidation except for deliberate seeding. Account create/disable/enable/reset invalidates the account list; patch or invalidate auth status only when the current account changes.
- Keep a one-time temporary password in local dialog state only. Never place it in the React Query cache, localStorage, a URL, a log, or a toast; clear it when the dialog closes.
- Derive role visibility from `useAuth` (`isRoot`) and the Settings section `roles` field. Hidden deep links fall back to the first visible Settings tab, and a direct `/accounts` visit redirects a normal user to `/profile`.
- All interface copy goes through `src/app/i18n`; add keys to English and both Chinese locales. Never hardcode user-facing labels, ARIA text, toasts, or errors.
- Every workspace owns its `page.tsx`, `component/`, `hook/`, and page CSS. Only reusable primitives belong in `src/app/component/`.
- Prefer the design tokens and shared primitives in `src/styles/` and `src/app/component/`. Do not add a second styling system.
- Keep TypeScript strict: no `any`, use type-only imports, and preserve the security and sanitization lint rules.
- Rebuild and commit `dist/` after frontend changes. Commit `dist/pdfjs/` whenever the generated PDF.js assets change; never hand-edit either output.

## Verification

```bash
cd frontend
bun run lint
bun run typecheck
bun run i18n:check
bun run build
```

A successful build must leave the expected source, `dist/`, and generated PDF.js asset changes in the working tree before committing.

## Related guides

- [Repository](../AGENTS.md)
- [Application layer](./src/app/AGENTS.md)
- [Global styles](./src/styles/AGENTS.md)
