# frontend/src/app/i18n/ — Agent Guide

The interface internationalization layer. It provides the typed translator, locale persistence and detection, locale-aware formatters, backend error/status mapping, and the English, Traditional Chinese, and Simplified Chinese dictionaries. It uses no external i18n package.

## Purpose

- Expose `useI18n()` with the active locale, `t`, and `Intl` formatters.
- Resolve dot-path keys from the active locale, then English, then the key itself.
- Keep all interface copy synchronized across `en`, `zh-TW`, and `zh-CN`.
- Translate known backend error codes and service-state values.
- Persist the reader's choice and keep `document.documentElement.lang` correct.

User-authored content, file and memory names, citations, model/provider names, tool names, URLs, code, and raw server detail are not translated.

## Architecture

- **Provider:** `I18nProvider.tsx` is the outermost app provider. It initializes from stored preference, then browser languages, then English. On change it updates the non-React active locale, document language, page title, and `localStorage` key `apsor-archive.locale`.
- **Lookup:** `translate.ts` walks dot paths such as `core.nav.library`. It falls back to English and then the key, and substitutes `{name}` placeholders from the optional variables object.
- **Locales:** `locale.ts` defines `LOCALES`, native option labels, detection (`zh-TW`/`zh-Hant`, `zh-CN`/`zh-Hans`, `en`), storage, and document-language application. A bare `zh` resolves to Traditional Chinese.
- **Dictionaries:** `locales/index.ts` combines seven namespaces (`core`, `chat`, `library`, `memory`, `insights`, `settings`, `systemPrompt`) for each locale. `TranslationKey` is derived from the English dictionary, so English is the type-level source of truth.
- **Parity:** `scripts/check-i18n.ts` flattens each namespace and reports missing or extra keys against English. Empty placeholder namespaces pass; a namespace with keys must match across all locales.
- **Errors:** `errors.ts` maps stable backend codes to `core.errors.*`, then shows the server detail verbatim for unknown codes, then a localized generic message. Provider/server text is never translated.
- **Statuses:** `status.ts` localizes the known service-state vocabulary and leaves unknown values verbatim.
- **Formatting:** `format.ts` creates `Intl.DateTimeFormat`, `Intl.NumberFormat`, and `Intl.RelativeTimeFormat` instances once per locale change.

## Key files

- `I18nProvider.tsx` — locale state, translator, formatters, document metadata, and `useI18n`.
- `locale.ts` — supported locales, native labels, detection, storage, and `lang`.
- `translate.ts` — dot-path lookup, interpolation, fallback, and active-locale bridge for non-React modules.
- `format.ts` — date, date-time, number, and relative-time formatters.
- `errors.ts` — `ApiError` code mapping and the hook/plain-module variants.
- `status.ts` — service-state localization.
- `locales/index.ts` — dictionary composition, namespace list, key flattening, and parity helpers.
- `locales/en/*.ts` — English source-of-truth namespace files.
- `locales/zh-TW/*.ts` — Traditional Chinese namespace files.
- `locales/zh-CN/*.ts` — Simplified Chinese namespace files.
- `../../../scripts/check-i18n.ts` — locale key-parity check.

## Conventions

- Route every user-visible string through `t`: labels, descriptions, empty states, hints, validation, toasts, `title`, `aria-label`, and `aria-description`.
- Add the English key first, then add the identical key path to both Chinese dictionaries. Keep the object shape and semantic grouping aligned.
- Use semantic keys, not English sentences. Use `{name}` interpolation and paired `One`/`Other` keys for counts.
- Run `bun run i18n:check` after any dictionary change. It checks key parity, not wording or placeholder quality.
- Use `useI18n()` inside components and `translateApiError` for mapped failures. Use `getActiveLocale`/`translateApiErrorWithActiveLocale` only in plain modules that cannot call hooks.
- Do not read dictionaries directly from UI code or duplicate a translation. Import the typed `TranslationKey` when a key must be passed around.
- Use provider formatters (`formatDate`, `formatDateTime`, `formatNumber`, `formatRelative`) instead of ad hoc date or number formatting.
- Keep locale native labels (`English`, `繁體中文`, `简体中文`) untranslated so readers recognize their own language.
- Add a namespace by creating it in all three locale directories, importing it in `locales/index.ts`, and extending both `TranslationDictionary` and `NAMESPACES`.
- Add a locale by extending `LOCALES`, adding every namespace file, wiring the dictionary and native option label, then running the key check.
- Do not translate user content or server/provider text. Do not assume the active translation exists; the English fallback is intentional.

## Verification

```bash
cd frontend
bun run i18n:check
bun run typecheck
bun run lint
```

Also switch all three locales on `/settings` and inspect auth, route errors, toasts, validation, and the Library, Settings, and Chat surfaces.

## Related guides

- [Application layer](../AGENTS.md)
- [Library](../library/AGENTS.md)
- [Settings](../settings/AGENTS.md)
- [Global styles](../../styles/AGENTS.md)
