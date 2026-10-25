import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { createFormatters, type I18nFormatters } from "./format";
import {
  applyDocumentLanguage,
  getInitialLocale,
  storeLocale,
} from "./locale";
import type { Locale, TranslationKey } from "./locales";
import {
  setActiveLocale,
  translate,
  type InterpolationVars,
} from "./translate";

/** The locale, translator, and locale-aware formatters available to any page. */
export interface I18nContextValue extends I18nFormatters {
  readonly locale: Locale;
  readonly setLocale: (locale: Locale) => void;
  readonly t: (key: TranslationKey, vars?: InterpolationVars) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

/**
 * Owns the active interface language. It is the outermost app provider so
 * auth screens, route errors, and toasts can all translate.
 */
export function I18nProvider({ children }: { readonly children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  const setLocale = useCallback((next: Locale) => {
    // Update the non-React translator before rendering descendants so error
    // helpers and other plain modules switch in the same paint.
    setActiveLocale(next);
    setLocaleState(next);
  }, []);

  const t = useCallback(
    (key: TranslationKey, vars?: InterpolationVars) =>
      translate(locale, key, vars),
    [locale],
  );

  const formatters = useMemo(() => createFormatters(locale), [locale]);

  useEffect(() => {
    setActiveLocale(locale);
    applyDocumentLanguage(locale);
    storeLocale(locale);
    document.title = `${translate(locale, "core.app.name")} — ${translate(
      locale,
      "core.app.studio",
    )}`;
  }, [locale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t,
      ...formatters,
    }),
    [formatters, locale, setLocale, t],
  );

  return <I18nContext value={value}>{children}</I18nContext>;
}

/** Reads the interface language and translation helpers. */
export function useI18n(): I18nContextValue {
  const value = use(I18nContext);
  if (!value) {
    throw new Error("useI18n must be used inside I18nProvider.");
  }
  return value;
}
