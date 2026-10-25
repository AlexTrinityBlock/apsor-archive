import { LOCALES, type Locale } from "./locales";

/** localStorage key for the reader's interface language. */
export const LOCALE_STORAGE_KEY = "apsor-archive.locale";

/** A language offered by the Settings language panel. */
export interface LocaleOption {
  readonly id: Locale;
  readonly nativeLabel: string;
  readonly code: string;
}

/**
 * Native labels are intentionally identical in every interface language:
 * readers should recognize their own language without translating it first.
 */
export const LOCALE_OPTIONS: readonly LocaleOption[] = [
  { id: "en", nativeLabel: "English", code: "en" },
  { id: "zh-TW", nativeLabel: "繁體中文", code: "zh-TW" },
  { id: "zh-CN", nativeLabel: "简体中文", code: "zh-CN" },
];

/** Narrows any stored or navigator value to a supported locale. */
export function isLocale(value: unknown): value is Locale {
  return (
    typeof value === "string" &&
    (LOCALES as readonly string[]).includes(value)
  );
}

/** Reads the persisted locale; a blocked storage API is not fatal. */
export function readStoredLocale(): Locale | null {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return isLocale(stored) ? stored : null;
  } catch {
    return null;
  }
}

function localeFromTag(tag: string): Locale | null {
  const normalized = tag.trim().toLowerCase();
  if (normalized.startsWith("zh")) {
    if (
      normalized.includes("hans") ||
      normalized.startsWith("zh-cn") ||
      normalized.startsWith("zh-sg")
    ) {
      return "zh-CN";
    }
    if (
      normalized.includes("hant") ||
      normalized.startsWith("zh-tw") ||
      normalized.startsWith("zh-hk") ||
      normalized.startsWith("zh-mo")
    ) {
      return "zh-TW";
    }
    // A bare `zh` most often means the reader's regional convention; the
    // archive's primary Chinese audience is Traditional Chinese.
    return "zh-TW";
  }
  if (normalized.startsWith("en")) {
    return "en";
  }
  return null;
}

/** Detects the closest supported locale from the browser language list. */
export function detectLocale(): Locale {
  if (typeof navigator === "undefined") {
    return "en";
  }
  const tags = [...(navigator.languages ?? []), navigator.language].filter(
    (tag) => tag.length > 0,
  );
  for (const tag of tags) {
    const locale = localeFromTag(tag);
    if (locale !== null) {
      return locale;
    }
  }
  return "en";
}

/** Stored preference first, then browser detection, then English. */
export function getInitialLocale(): Locale {
  return readStoredLocale() ?? detectLocale();
}

/** Persists the choice for later reloads; storage failures are ignored. */
export function storeLocale(locale: Locale): void {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // A private browser may reject storage; the current tab still switches.
  }
}

/** Sets the document language so fonts, hyphenation, and AT follow the UI. */
export function applyDocumentLanguage(locale: Locale): void {
  if (typeof document !== "undefined") {
    document.documentElement.lang = locale;
  }
}
