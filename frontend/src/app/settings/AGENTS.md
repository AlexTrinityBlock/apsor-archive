# frontend/src/app/settings/ — Agent Guide

The `/settings` system-configuration workspace. It owns the top settings tab strip, provider registry, prompt configuration, diagnostics, runtime limits, maintenance, and interface language. Each tab mounts one section component at a time.

## Purpose

- Configure the four provider capability slots without exposing stored secrets.
- Edit durable system prompts and frequently used prompts.
- Inspect health, AI configuration, vector state, and reindex status.
- Persist agent and ingestion runtime limits, including the vision description language, with validation and reset-to-default.
- Switch interface language immediately.
- Keep every section directly linkable through its established hash id.

Settings does not own backend validation, generated API definitions, or global i18n dictionaries. Those live in the backend and `../i18n/`.

## Architecture

- **Top tab workspace:** `page.tsx` renders `PageHeader`, `SettingsTabs`, and exactly one panel. Do not restore the old left anchor navigation or render all sections with hidden inactive panels.
- **Section registry:** `component/settings-sections.ts` is the source of order, ids, label keys, role visibility, and visible indices. `SECTION_PANELS` in `page.tsx` is an exhaustive `Record<SettingsSectionId, ComponentType>`. A new tab needs entries in both places and a `roles` value.
- **Role visibility:** root sees every tab; a normal account sees only Frequent prompts and Language (the personal tabs). Hidden deep links fall back to the first visible tab and rewrite the hash. Root-only account management lives at `/accounts`, not in Settings.
- **Stable ids:** section ids are `settings-system-prompt`, `settings-frequent-prompts`, `settings-providers`, `settings-diagnostics`, `settings-agent-runtime`, `settings-ingest-runtime`, `settings-maintenance`, and `settings-language`. An id is both the URL hash and the active tabpanel id.
- **Deep links:** `parseSettingsSectionHash` maps a known hash to its tab and falls back to the first section. Existing links such as `/settings#settings-language` and the chat link to `#settings-frequent-prompts` must keep working.
- **Navigation:** clicking a tab uses React Router `navigate()` with the section hash, updates local state, and resets scroll. A `location.hash`/`location.key` sync plus `hashchange` and `popstate` listeners keep direct hash edits, sidebar navigation, and browser back/forward in sync.
- **Unknown hashes:** only an empty hash or a known `settings-*` section may change the active tab. Unknown hashes such as the global skip link's `#main-content` are ignored and must not reset the tab or scroll position.
- **Scroll reset:** `useLayoutEffect` resets both `window` and the `.app-page` canvas to the top with instant behavior after a tab change, preventing the fixed shell from retaining a stale scroll offset.
- **ARIA:** the strip is `role="tablist"` with `aria-orientation="horizontal"`; each button is a `role="tab"` with `aria-selected`, roving `tabIndex`, `aria-controls`, and a stable id. The sole rendered section is a `role="tabpanel"` labelled by the active tab. The panel itself is not a tab stop; do not add `tabIndex=0`.
- **Keyboard:** ArrowLeft/ArrowRight wrap through sections, Home selects the first, End selects the last, and focus follows selection. If focus was inside the tablist before a popstate/hashchange, the strip restores focus to the new active tab after native fragment navigation; it never steals focus from a skip link or the page body. The selected tab is centered by measuring the strip with a `ResizeObserver`, but only when it is actually clipped.
- **Horizontal overflow:** the tab strip never wraps. It scrolls horizontally and keeps the active tab visible; the page itself must not gain horizontal overflow at 390 px.
- **Sticky:** the tab strip stays sticky at the top of `.app-page` so a long panel does not force a scroll back to the top before switching sections.
- **Active-only mount:** switching tabs unmounts the previous panel. Panel-local drafts, open dialogs, and in-flight UI state are intentionally not preserved across tabs. Do not store cross-tab workflows in a panel.
- **Panel data:** panels own their generated queries and mutations. Runtime wrappers in `RuntimeSettingsPanels.tsx` load the singleton settings row, cache the update/reset response, and refetch active queries. Provider changes refresh registry, AI status, health, and stats through `settings-invalidation.ts`.
- **Panels:** System prompt (ordered sections), Frequent prompts, Provider registry (chat, embedding, web search, web fetch), Diagnostics (health/stats/status/reindex), Agent runtime, Ingestion runtime (runtime settings plus the vision prompt editor), Maintenance (access notes and version), and Language.
- **Forms:** validate ranges and cross-field rules before save, disable save for unchanged drafts, block invalid payloads, send full update payloads, and persist reset through the reset endpoint rather than only clearing local state. The vision prompt editor redirects an invalid submit to the first broken tab and focuses that textarea.
- **Vision extraction:** the ingestion panel's third group is one full-width free-text `Description language` field. Canonical English suggestions (`English`, `Traditional Chinese`, `Simplified Chinese`, `Japanese`, `Korean`, `Spanish`, `French`, `German`) are offered through a datalist, but the stored value is never localized. Trim before save, require 1–80 characters after trimming, and keep it inside the existing singleton payload rather than adding a second config field or settings tab.
- **Vision prompt editor:** `IngestRuntimeSection` stacks the existing runtime panel and a sibling `VisionPromptSettingsPanel` inside `settings-ingest-runtime`; do not add another Settings tab. The prompt panel owns `GET`/`PUT /settings/ingest/vision-prompts`, a separate query/mutation from the runtime snapshot, so resetting runtime values never clears custom prompts and saving prompts never re-ingests files. Images and Scanned pages are two tabs over one form whose parent holds both drafts; switching tabs must not lose edits. Save mirrors the backend's non-empty, 32K, and required-JSON-key checks; safety warnings are non-blocking. Restore-default only edits the draft, and there is no prompt history, diff, activation, or rollback UI. Prompt bodies are data and must never be passed through `t()`; only labels, hints, errors, and warnings are localized. The `<details>` technical section shows the saved template fingerprints, not a version history.
- **Secrets:** provider read models expose only `key_hint`/`key_source`. Never render or request full keys.

## Key files

- `page.tsx` — active section, hash synchronization, panel mounting, and scroll reset.
- `component/SettingsTabs.tsx` — horizontal scroll strip, keyboard navigation, ARIA, and active-tab centering.
- `component/settings-sections.ts` — section order, ids, labels, defaults, and hash parsing.
- `component/RuntimeSettingsPanels.tsx` — agent/ingestion query, update, and reset wrappers.
- `component/AgentRuntimePanel.tsx` — context budget, tool execution, compaction fields, and validation.
- `component/IngestRuntimePanel.tsx` — worker, chunking, and vision description-language fields, validation, and warnings.
- `component/IngestRuntimeSection.tsx` — stacks the ingestion runtime panel and the vision prompt editor in one Settings tab.
- `component/VisionPromptSettingsPanel.tsx` — prompt query/save mutation, both drafts, status, contract notice, and fingerprint details.
- `component/VisionPromptEditor.tsx` — one full-prompt textarea with count, per-field error, safety warnings, and restore-default.
- `component/vision-prompt-utils.ts` — prompt draft matching, required-key validation, warning detection, and short fingerprints.
- `component/ProviderVaultPanel.tsx` — four capability groups, provider CRUD, testing, and reindexing.
- `component/SystemPromptPanel.tsx` — sortable prompt sections and their dialogs.
- `component/FrequentlyUsedPromptsPanel.tsx` — saved prompt CRUD.
- `component/DiagnosticsPanel.tsx` — live health, stats, AI, vector, and reindex surfaces.
- `component/MaintenancePanel.tsx` — access notes, version badge, and colophon.
- `component/LanguagePanel.tsx` — immediate locale switching.
- `component/settings-utils.ts` — status tones, labels, and localized API errors.
- `component/settings-invalidation.ts` — scoped provider and reindex invalidation.
- `settings.css` — page composition, tab strip, runtime forms, and responsive rules.

## Conventions

- Keep the settings page a tab workspace. Do not reintroduce `SettingsNav`, anchor scrolling, or all-panels mounting.
- Preserve existing section ids once shipped. They are public deep links and the tabpanel ids.
- When adding a section: add it to `SETTINGS_SECTIONS`, add its translation key under `core.settingsNav.*` in all three locales, add its panel to `SECTION_PANELS`, and verify the hash round trip.
- Let only the active panel mount. Do not hide inactive panels with CSS or `hidden`.
- Keep tab selection in the hash; do not create a separate route per section.
- Invalidate narrowly with generated query keys. Do not use a blanket cache reset after settings mutations.
- Use `SwitchField`, `RuntimeNumberField`, `RuntimeTextField`, `Panel`, `Button`, `StatusPill`, and shared error/empty patterns rather than new controls.
- Keep the vision description language a free-text value with canonical English suggestions; translate only the label, hint, and error copy. The field keeps the full seven-field ingestion snapshot and applies to future ingests only.
- Keep prompt persistence separate from `PUT /settings/ingest`: the vision prompt editor sends both prompts in one request to its own endpoint. Do not add prompt fields to the runtime update/reset payload, and do not add a prompt version table or history UI.
- Inspect both prompt drafts before save, switch to the first invalid tab, and keep per-field errors and character counts associated through `aria-describedby`. Use 16px textarea text at 720px and below.
- Treat destructive actions (reset, delete, deactivate, reindex, seed) as confirmed actions with pending and error states.
- Keep labels, hints, validation messages, and ARIA copy under the `settings` or `core` namespaces; no hardcoded UI strings.
- Reuse `settings.css`; new page CSS belongs in this workspace, not global styles. Respect reduced motion and avoid horizontal page overflow.
- Do not require backend changes to add a tab; the tab shell is frontend-only unless a panel adds a new API.

## Verification

```bash
cd frontend
bun run lint
bun run typecheck
bun run i18n:check
bun run build
```

Verify direct hash links, tab clicks, back/forward, Arrow/Home/End navigation, active-tab centering, rapid tab switching, language switching, and the 390 px layout.

## Related guides

- [Application layer](../AGENTS.md)
- [Library](../library/AGENTS.md)
- [Internationalization](../i18n/AGENTS.md)
- [Global styles](../../styles/AGENTS.md)
