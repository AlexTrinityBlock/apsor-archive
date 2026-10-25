# frontend/src/styles/ — Agent Guide

The global visual foundation for the archive: design tokens, reset and typography, the application shell layout, shared component primitives, local font faces, and global accessibility defaults. Page-specific CSS is owned by each workspace, not here.

## Purpose

- Define the single light-only archive palette, typography, spacing, shape, motion, and layer scale.
- Style the fixed shell, navigation rail, mobile drawer, canvas, and content containers.
- Provide reusable classes for buttons, badges, panels, tabs, modals, tables, empty states, toasts, citations, metadata, and pagination.
- Serve local fonts without a network dependency.
- Centralize reduced-motion and focus behavior.

This directory does not own workspace composition. Library, Settings, Chat, and other pages add their own prefixed styles under their page directories.

## Architecture

- `fonts.css` — local `@font-face` declarations for Inter and JetBrains Mono, loaded from `/fonts/`.
- `tokens.css` — canonical colors, type stacks, rail and content widths, spacing, radii, transitions, and z-index tokens. Legacy aliases keep older surfaces coherent while new code should prefer canonical tokens.
- `base.css` — box sizing, reset, full-height root, paper canvas, typography defaults, links, focus-visible ring, selection, scrollbars, utility classes such as `.visually-hidden`, and reduced-motion overrides.
- `layout.css` — `.app-shell`, collapsible `.nav-rail`, `.mobile-bar`, drawer/scrim, `.app-main`, `.app-page` scroll ownership, content containers, and the 980/600 px shell breakpoints.
- `components.css` — shared visual primitives and responsive rules for them. `app/component/*.css` holds composition for specific shared React primitives; page CSS lives with its page.
- `index.css` — imports the layers in order: fonts, tokens, base, layout, components. `main.tsx` imports only this file.

The application is light-only: `tokens.css` declares `color-scheme: light` and there is no active theme switcher. Do not add dark-mode selectors or a second palette without an explicit product decision.

## Key files

- `index.css` — the global import order.
- `fonts.css` — self-hosted font faces and fallback behavior.
- `tokens.css` — the canonical design-token source, including the layer scale.
- `base.css` — reset, editorial defaults, focus, scrollbars, and motion preferences.
- `layout.css` — shell, rail, mobile drawer, canvas, and responsive layout.
- `components.css` — shared primitives and their breakpoints.
- `../app/component/shared.css` — shared page-header, query-state, and fallback composition.
- `../app/component/ContextMenu.css` — portal menu styling and its reviewed z-index exception.

## Conventions

- Use existing tokens for color, type, spacing, radius, motion, and z-index. Add a token in `tokens.css` instead of scattering a new raw value through page CSS.
- Prefer canonical names such as `--mono-*`, `--accent-*`, `--content-*`, and `--z-*`. Legacy aliases exist for older surfaces, not as the preferred API for new work.
- Keep global element styling in `base.css` and shell structure in `layout.css`. Do not add page-specific selectors to these files.
- Give page CSS a workspace prefix and import it from that page or its owning component. A shared primitive belongs in `components.css` or `app/component/`; it does not belong in a page stylesheet.
- Do not introduce Tailwind, CSS modules, a preprocessor, or runtime CSS-in-JS. The project uses plain CSS imported by Vite.
- Preserve the shell's scroll model: `html`/`body` do not scroll; `.app-page` is the normal canvas, while Chat and Library use `.app-page--fixed`. Do not add another full-viewport scroll container.
- Use `100dvh` for full-height surfaces and account for the mobile bar below 980 px.
- Prevent horizontal overflow. Use `min-width: 0`, wrapping, and truncation where headers, paths, tabs, and tables can grow. Check 390 px, 761 px, 980 px, and desktop widths.
- Reuse the established breakpoints (980 for shell, 900/760/720 for content and modals, 560/600 for compact layouts) rather than adding one-off widths.
- Respect the z-index scale. Modals use `--z-modal`, drawers `--z-drawer`, the rail `--z-rail`, and toasts `--z-toast`. Do not invent large values; the context menu's 1400 is a documented portal exception above modals and toasts.
- Keep focus-visible styling intact and preserve the global reduced-motion override. Every interactive page style must remain keyboard-reachable.
- Use local fonts only. Do not add remote font URLs or third-party CSS imports that block offline use.

## Verification

```bash
cd frontend
bun run lint
bun run typecheck
bun run build
```

Inspect the shell and affected primitives at 390, 761, 980, and 1280 px, with keyboard focus visible and reduced motion enabled. Confirm there is no page-level horizontal scrollbar.

## Related guides

- [Frontend](../../AGENTS.md)
- [Application layer](../app/AGENTS.md)
- [Library](../app/library/AGENTS.md)
- [Settings](../app/settings/AGENTS.md)
