# frontend/src/app/companion/ — Agent Guide

The chat companion: a marionette librarian that floats beside the chat box, mirrors what the agent is doing, and carries a persona and lore. It is a supporting domain (like `viewer/`), not a route. Chat mounts it once; Settings hosts its configuration tab.

## Architecture

- **Mount:** `component/ChatCompanion.tsx` is the only chat-page mount. It takes the live stream, the composer draft, and a conversation key — state the page already has — so `chat/` never imports companion internals. `ToolStepCard` additionally renders `CompanionLoreTrace` inside a tool step's details.
- **State machine:** `actions.ts` defines the stable action ids (shared with manifests, uploads, and the agent's `companion_action` tool), priorities, fallbacks, and the tool→pose map. `director.ts` is pure: `desiredPose` picks the highest-priority signal and `advanceDirector` enforces a ≈900 ms minimum dwell (held, failure, and approval skip it). `director-engine.ts` owns clocks and timers and is read through `useSyncExternalStore`; React only feeds observations.
- **Agent gestures:** a `companion_action` tool call (`{action}`) overrides automatic poses for ~3 s. A finished `search_knowledge` step whose data carries `lore` earns a brief soft `reading` pose.
- **Placement:** `layout.ts` is pure geometry. Positions are saved per breakpoint as a dock line (`viewport-left/right`, `panel-left/right`) plus a vertical fraction, so they survive resizes. Drops project the throw velocity and snap to the nearest dock line; the composer band is never covered. Covering the reading column turns the figure into a peek (slide at window edges, shrink and fade elsewhere) until hovered or focused; an open modal hides it; phones always start peeking.
- **Animation:** one `requestAnimationFrame` loop per stage writes CSS variables and SVG string paths directly (spring sway from drag velocity plus breathing). Poses crossfade only after every frame of the next clip has decoded (`frame-cache.ts`). Multi-frame clips play at the manifest fps, including `pingpong`. Motion is `full`, `reduced` (still poses, no effects), or `off`, and the OS reduced-motion request caps it at `reduced`.
- **Assets:** built-in presets live in `public/companions/<id>/` with `manifest.json` and an `index.json` list. Frame extensions come from the manifest (AVIF or WebP); never hard-code them. `manifest.ts` validates untrusted manifests: plain file names inside the character folder, same-origin `/api/` paths, or `blob:` URLs only.
- **Data layer:** `api.ts` is the single seam to the backend. Presets are a deliberate same-origin static-asset fetch. Custom companions (`listCompanions`, `createCompanion`, `uploadCompanionFrames`, …), preferences (`getCompanionPreference` / `updateCompanionPreference`), and the story (`getCompanionPersona` …, `listCompanionLore` …) are behind `CUSTOM_COMPANIONS_SUPPORTED` / `COMPANION_STORY_SUPPORTED`; until the generated hooks exist, preferences use a per-account local store and the editors keep in-tab drafts.
- **Story:** the persona and lore are authored content and are shown exactly as written, never translated. Lore is never styled as a citation or archive evidence; in chat it appears only in the tool-step details, labelled as the librarian's own memory, and the answer retells it in the librarian's voice.

## Conventions

- Keep pure logic in plain modules with colocated `bun:test` tests (`*.test.ts`).
- Never read refs or call `Date.now()` during render; timers belong to the engine or to effects.
- Only `ChatCompanion` and `CompanionLoreTrace` may be imported from `chat/`; keep those call sites one line each.
- Every UI string lives in the `companion` i18n namespace (plus `core.settingsNav.companion`); character names are data.
- Colors come from tokens; a character's accent is manifest data exposed as `--companion-accent`.
