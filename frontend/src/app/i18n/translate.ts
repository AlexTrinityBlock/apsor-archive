import { getInitialLocale } from "./locale";
import { dictionaries, type Locale, type TranslationKey } from "./locales";

/** Values substituted into `{name}` placeholders. */
export type InterpolationVars = Readonly<Record<string, string | number>>;

/** The translate function exposed by `useI18n()`. */
export type Translate = (key: TranslationKey, vars?: InterpolationVars) => string;

function lookup(dictionary: unknown, key: string): string | null {
  let current: unknown = dictionary;
  for (const segment of key.split(".")) {
    if (typeof current !== "object" || current === null) {
      return null;
    }
    current = (current as Readonly<Record<string, unknown>>)[segment];
  }
  return typeof current === "string" ? current : null;
}

function interpolate(template: string, vars?: InterpolationVars): string {
  if (!vars) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = vars[name];
    return value === undefined ? match : String(value);
  });
}

/**
 * Resolves a dot-path key against the active locale, then English, then the
 * key itself. This keeps missing translations visible without breaking a page.
 */
export function translate(
  locale: Locale,
  key: TranslationKey,
  vars?: InterpolationVars,
): string {
  const active = lookup(dictionaries[locale], key);
  if (active !== null) {
    return interpolate(active, vars);
  }
  const fallback = lookup(dictionaries.en, key);
  if (fallback !== null) {
    return interpolate(fallback, vars);
  }
  return key;
}

let activeLocale: Locale | null = null;

/** Keeps non-React helpers (error mapping) aligned with the provider. */
export function setActiveLocale(locale: Locale): void {
  activeLocale = locale;
}

/** The current locale for non-React helpers, detected on first use. */
export function getActiveLocale(): Locale {
  return activeLocale ?? getInitialLocale();
}
